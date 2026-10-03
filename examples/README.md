# Example timecode lists

## `sample-schedule.tsv`

A day from WikiConference India 2026, tab-separated, as exported from a
spreadsheet. This is the full shape vcut understands:

| Column | Required | What it is |
| --- | --- | --- |
| `programme` | recommended | The session title, used for the file name |
| `start_time` | **yes** | Where the clip starts, `HH:MM:SS` |
| `end_time` | **yes** | Where it ends, `HH:MM:SS` |
| `eventyay_id` | no | The talk code, used to fetch metadata |
| `author` | no | Speakers, used when the schedule has none |

Several rows deliberately have no `eventyay_id` — a cultural performance, a
pre-recorded video, a community meet-up. These are not errors: those clips are
cut like any other and fall back to the title and author in this file.

Pair it with the event `india26` to see metadata fetched for the rows that do
have a code.

## `sample-minimal.csv`

The smallest thing that works: comma-separated, titles and times only. Use
this shape when there is no schedule to look anything up in.

## Notes on the format

- Tabs, commas, semicolons and pipes are all detected automatically.
- Column names are matched loosely, so `title`, `session` or `room_name` work
  as well as `programme`, and `start`/`in`/`from` as well as `start_time`.
- Times may be `HH:MM:SS`, `MM:SS`, or a plain number of seconds.
- Columns vcut does not recognise are carried through untouched.
