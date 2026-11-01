"""mdkp: 0-1 multidimensional knapsack (maximize total profit under m capacity dimensions).

Pick a subset S of n items maximizing sum of values, subject to
sum of weights per dimension <= capacity, for every one of m dimensions.
Reference solvers: greedy (always feasible) and HiGHS MIP (strong anchor).
"""
