#!/usr/bin/env python3

import argparse
from datetime import datetime
from bcc import BPF, USDT
import math
import subprocess
import textwrap
import threading


class MysqlQueryTracer(object):
  BPF_PROGRAM = textwrap.dedent("""
  #include <uapi/linux/ptrace.h>
  #define THRESHOLD %(threshold)d

  struct data_t {
    u64 timestamp;
    u64 time_taken;

    char query[256];
    u64 query_length;
    u8 query_truncated;

    // Needed for USDT, as the query is read in the done probe
    // Also if I allocate a local variable directly for this addr, and then
    // try to read data with the local variable for the USDT case, I get a
    // BPF validator error for some reason.
    char* query_addr;
  };

  // To store the data between the start and end of the query.
  // The key is the thread id.
  BPF_HASH(data_tmp, u32, struct data_t);
  BPF_PERF_OUTPUT(events);

  int do_trace_start_usdt(struct pt_regs *ctx) {
    u32 tid = bpf_get_current_pid_tgid();
    struct data_t data = {};
    data.timestamp = bpf_ktime_get_ns();

    bpf_usdt_readarg(1, ctx, &data.query_addr);

    data_tmp.update(&tid, &data);
    return 0;
  }

  int do_trace_done_usdt(struct pt_regs *ctx) {
    u32 tid = bpf_get_current_pid_tgid();
    struct data_t* data = data_tmp.lookup(&tid);
    if (data == 0) {
      return 0; // Missing do_trace_start?
    }

    data->time_taken = bpf_ktime_get_ns() - data->timestamp;
    if (data->time_taken >= THRESHOLD) {
      // Reading it here is more performant if THRESHOLD is non-zero.
      data->query_length = bpf_probe_read_user_str(&data->query, sizeof(data->query), (void*) data->query_addr);
      data->query_truncated = 0;
      // Compared to the uprobe method, I think this is technically off by 1, but it is close enough...
      if (data->query_length == sizeof(data->query) && data->query[data->query_length-1] != '\\0') {
        data->query_truncated = 1;
      }

      events.perf_submit(ctx, data, sizeof(*data));
    }

    return 0;
  }

  #define M_QUERY_STRING_OFFSET %(m_query_string_offset)d
  #define M_QUERY_LENGTH_OFFSET %(m_query_length_offset)d

  int do_trace_start_uprobe(struct pt_regs *ctx) {
    u32 tid = bpf_get_current_pid_tgid();
    struct data_t data = {};
    data.timestamp = bpf_ktime_get_ns();

    void* thd_addr = (void*) PT_REGS_PARM1(ctx);

    // Read the query as the mysql_execute_command is started as opposed to
    // returned, because the function might clear the query variable (but that
    // might only be applicable to dispatch_command instead of
    // mysql_execute_command). See:
    // https://github.com/iovisor/bcc/blob/c9805f4/tools/dbslower.py#L95-L97
    void* query_addr;

    // Read the query length, which can be useful to determine if the query
    // returned by BPF is truncated.
    bpf_probe_read_user(&data.query_length, sizeof(data.query_length), thd_addr + M_QUERY_LENGTH_OFFSET);

    // Read the address of the pointer to const char of the query itself
    bpf_probe_read_user(&query_addr, sizeof(query_addr), thd_addr + M_QUERY_STRING_OFFSET);

    data.query_truncated = data.query_length > sizeof(data.query_length);

    // Read the actual query string.
    bpf_probe_read_user_str(&data.query, sizeof(data.query), query_addr);

    data_tmp.update(&tid, &data);
    return 0;
  }

  int do_trace_done_uprobe(struct pt_regs *ctx) {
    u32 tid = bpf_get_current_pid_tgid();
    struct data_t* data = data_tmp.lookup(&tid);
    if (data == 0) {
      return 0; // Missing do_trace_start?
    }

    data->time_taken = bpf_ktime_get_ns() - data->timestamp;
    if (data->time_taken >= THRESHOLD) {
      events.perf_submit(ctx, data, sizeof(*data));
    }

    return 0;
  }
  """)

  MODE_USDT = "usdt"
  MODE_UPROBE = "uprobe"

  @staticmethod
  def argparser(description="trace MySQL query via USDT or uprobe"):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("-m", "--mode", choices=[MysqlQueryTracer.MODE_USDT, MysqlQueryTracer.MODE_UPROBE], default="usdt", help="the mechanism to trace with")
    parser.add_argument("-p", "--path", default="/usr/local/mysql/bin/mysqld", help="path to the mysqld binary")
    parser.add_argument("-t", "--threshold", type=int, default=0, help="minimum threshold to trace in ms")
    parser.add_argument("pid", nargs="?", type=int, default=1, help="the pid to trace")
    return parser

  def __init__(self, args):
    self.threshold = args.threshold * 1000000
    self.path = args.path
    self.pid = args.pid
    self.mode = args.mode

    self.mysql_version = self._determine_mysql_version()

    self._bpf_program = self.BPF_PROGRAM % {
      "threshold": self.threshold,
      "m_query_string_offset": self._query_string_offset(),
      "m_query_length_offset": self._query_length_offset(),
    }

    if self.mode == self.MODE_USDT:
      self._u = USDT(pid=self.pid, path=self.path)
      self._u.enable_probe(probe="mysql:query__exec__start", fn_name="do_trace_start_usdt")
      self._u.enable_probe(probe="mysql:query__exec__done", fn_name="do_trace_done_usdt")
      usdt_contexts = [self._u]
    else:
      usdt_contexts = []

    self._b = BPF(text=self._bpf_program, usdt_contexts=usdt_contexts)
    if self.mode == self.MODE_UPROBE:
      for fname, _ in set(BPF.get_user_functions_and_addresses(self.path, r"\w+mysql_execute_command\w+")):
        self._b.attach_uprobe(name=self.path, sym=fname, fn_name="do_trace_start_uprobe")
        self._b.attach_uretprobe(name=self.path, sym=fname, fn_name="do_trace_done_uprobe")

  def run(self):
    # TODO: what's page_cnt
    self._b["events"].open_perf_buffer(self._on_event, page_cnt=64)
    while True:
      self._b.perf_buffer_poll()

  def on_event(self, event, **kwargs):
    """Override this function in a subclass to get custom aggregation behaviour"""
    print("{}\t{:.1f}\t{} ({})\t{}".format(
      datetime.fromtimestamp(event.timestamp / 1000000000),
      event.time_taken / 100000,
      event.query_length,
      event.query_truncated,
      event.query
    ))

  def _on_event(self, cpu, data, size):
    event = self._b["events"].event(data)
    self.on_event(event, cpu=cpu, data=data, size=size)

  def _query_string_offset(self):
    if self.mysql_version == "8.0":
      return 512
    elif self.mysql_version == "5.7":
      return 472

  def _query_length_offset(self):
    if self.mysql_version == "8.0":
      return 520
    elif self.mysql_version == "5.7":
      return 480

  def _determine_mysql_version(self):
    ret = subprocess.run([self.path, "--version"], check=True, capture_output=True)
    version_string = ret.stdout.decode("utf-8")
    if "8.0" in version_string:
      return "8.0"
    elif "5.7" in version_string:
      return "5.7"
    else:
      raise NotImplementedError("this script isn ot implemented for {}".format(version_string))


if __name__ == "__main__":
  args = MysqlQueryTracer.argparser().parse_args()
  t = MysqlQueryTracer(args)
  t.run()
