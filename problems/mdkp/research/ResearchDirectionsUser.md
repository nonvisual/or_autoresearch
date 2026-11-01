# Research directions, user (mdkp)

<!-- Written by the human owner. Agents READ but never WRITE this file.
     One idea per heading: "## U<n>: <one line>", free prose below.
     The file is re-read fresh every iteration, so edits mid-run are picked up. -->

## U1: LP-guided item priorities
Solve the LP relaxation once and order items by dual price / reduced cost
instead of the static profit-over-weight ratio; repair greedily to feasibility.

## U2: Local search on top of constructive solutions
Start from a greedy solution, then improve with swap and drop-add
neighborhoods under a fast incremental feasibility check.

## U3: MIP on the core subset
Fix the "easy" fraction of variables from a greedy pass and solve the
remaining core exactly with HiGHS under the remaining time budget.
