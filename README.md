MySQLd BPF testing
==================

MySQL 5.7 has [DTrace][1] support, which can be [used as USDT tracepoints][2].
Unfortunately, DTrace support was removed in 8.0, because presumably no one
used it, as DTrace is only recently supported on Linux. This repo has a BPF
program that can trace both via the DTrace tracepoints, as well as via
[uprobe][3].

[1]: https://dev.mysql.com/doc/refman/5.7/en/dba-dtrace-server.html
[2]: https://leezhenghui.github.io/linux/2019/03/05/exploring-usdt-on-linux.html#heading-how-does-dtrace-works-with-usdt
[3]: https://www.brendangregg.com/blog/2015-06-28/linux-ftrace-uprobe.html

DTrace/USDT
-----------

MySQL in 5.7 has built-in support for DTrace tracepoints. The tracepoints are
organized through the entire query process as follows:

![tracepoints](https://dev.mysql.com/doc/refman/5.7/en/images/dtrace-groups.png)

Based on experimentation, I've observed that prepared queries only fire the
`query-exec-start` and `query-exec-done` tracepoints and skip the `query-start`
and `query-done` tracepoints. So the scripts in this repo is based on
`query-exec-start` and `query-exec-done`.

References: 

- https://dev.mysql.com/doc/refman/5.7/en/dba-dtrace-mysqld-ref.html
- https://github.com/iovisor/bcc/blob/master/tools/dbslower.py
- https://github.com/iovisor/bcc/blob/master/examples/tracing/mysqld_query.py

UProbe
------

MySQL deprecated Dtrace in 5.7 and removed it in 8.0. This means that it can
no longer be traced via USDT. The present repo contains a BPF program that can
trace `query-exec-start` and `query-exec-done` via uprobe and the
`mysql_execute_command` function. The query is extracted by reading the first
argument of `mysql_execute_command` which is object of class `THD` (for 5.7 and
8.0 at least) and then finding the offset for the query in this class. This
means the script may have to change if MySQL version updates as the `THD` class
might change. USDT doesn't have this issue as the query is emitted from the
code. It also means that the more granular data available via dtrace will not
be easily (nor stably) exposable via the uprobe system.

To figure out that I had to trace the `mysql_execute_command` function:

1. I noted that in MySQL 5.7, the `query__exec__start` and `query__exec__done`
   tracepoints corresponds to the macro `MYSQL_QUERY_EXEC_START` and
   `MYSQL_QUERY_EXEC_END`.
2. By reading through the MySQL source code, one can see that there are four
   places where these tracepoints are placed: [1][1], [2][2], [3][3], [4][4].
   In every location, the function [`mysql_execute_command`][5] is called.
   Based on this information, it seems like `mysql_execute_command` is the
   function to trace if we want to replicate the `query__exec__*` tracepoints.
   - Caveat 1: There's [one more place][6] where `mysql_execute_command` is
     called that is not surrounded by the `query__exec__*` tracepoints. This
     edge case is not considered.
   - Caveat 2: The [dbslower][7] script from BCC's repo is tracing
     [`dispatch_command`][8] instead of `mysql_execute_command`. This function
     gets passed a `COM_DATA` union, which is the query string if the third
     argument (`command`) is `COM_QUERY`. This is probably easier to deal with
     than looking through the `THD` class as we are about to next. Not sure
     which function is better to trace, although [Brendon Gregg's MySQL
     flamegraph shows `dispatch_command` to be above
     `mysql_execute_command`][9].
3. The query string is stored in a member variable of the first argument, which
   is a pointer to the [`THD`][10] class. The member variable for the entire
   query string is called [`m_query_string`][11], which is itself a
   [`LEX_CSTRING`][12], which is a [`st_mysql_const_lex_string`][13] that has a
   pointer to const char and a uint64 length field. These are the fields we
   need to read in the BPF program in this repo.
4. To read the actual query string, we need to find the offset to
   `m_query_string`. To do this, I compiled Percona server 5.7.35-38 from
   source and used [`pahole`][14] to examine
   `sql/CMakeFiles/sql.dir/sql_class.cc.o` and found the following output
   which indicates that the query is at an offset of 472 bytes:
```
LEX_CSTRING                m_query_string;       /*   472    16 */
class String              m_normalized_query;    /*   488    32 */
```

The same process can be followed for any version of MySQL, and for any other
variables that one would like to look at (although the BPF program will have to
be changed).

I also saved a copy of the pahole output in this repo, under the `data`
directory.

[1]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sp_instr.cc#L1015-L1033
[2]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_cursor.cc#L118-L132
[3]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_parse.cc#L5583-L5601
[4]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_prepare.cc#L3979-L4010
[5]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_parse.cc#L2437-L5117
[6]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_prepare.cc#L3052
[7]: https://github.com/iovisor/bcc/blob/c9805f4/tools/dbslower.py
[8]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_parse.cc#L1219
[9]: https://www.brendangregg.com/FlameGraphs/cpu-mysql-updated.svg
[10]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_class.h#L1465
[11]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/sql/sql_class.h#L1523
[12]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/include/m_string.h#L243
[13]: https://github.com/mysql/mysql-server/blob/0ed6d65f4c60a38e77a672fc528efd3f44bc7701/include/mysql/mysql_lex_string.h#L33-L37
[14]: https://manpages.debian.org/bullseye/dwarves/pahole.1.en.html

Running this
------------

Setup:

```
$ docker-compose up -d
$ scripts/prepare-db mysql57
$ scripts/prepare-db mysql80
```

Loading MySQL with queries:

```
$ scripts/load-db mysql57 # For loading the 5.7 instance
$ scripts/load-db mysql80 # For loading the 8.0 instance.
```

Tracing every query:

```
$ scripts/trace-simple mysql57 -m usdt
$ scripts/trace-simple mysql57 -m uprobe
$ scripts/trace-simple mysql80 -m uprobe
```

Tracing with a historgram:

TODO
