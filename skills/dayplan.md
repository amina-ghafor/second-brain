# dayplan

Build today's plan from the calendar and the backlog. This is a read and a recommendation. Do not edit the backlog or the calendar.

## Read

- Today's calendar events: meetings, busy blocks, and the `[Reflow]` events the scheduler has already placed.
- `Backlog.md`, the Overdue and Due This Week sections.

## Produce, to the terminal

- The fixed points of the day in order, with the gaps between them.
- Which backlog tasks fit those gaps, matched on their time estimate.
- One task to start with, and the reason it is that one.
- Anything due this week that will not fit today, named now rather than found on Thursday.

## Rules

- Estimates come from the task's own `(1h)` or `(30m)` marker. If a task has none, treat it as 30 minutes and say so.
- If the day is already full, say that and name what gets dropped.
- One plan, not a set of options.
