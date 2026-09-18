# Binary String Construction

You are given the following process for constructing a binary string.

The process starts with a single digit, which can be either `0` or `1`.

For every subsequent iteration:

1. Take the current string.
2. Invert every bit (`0 → 1` and `1 → 0`).
3. Append the inverted string to the end of the current string.

For example, if we start with `1`:

Iteration 0: `1`
Iteration 1: `10`
Iteration 2: `1001`
Iteration 3: `10010110`

## Problem

Write a method that takes two inputs:

- `firstDigit` — the first digit of the string (`0` or `1`)
- `n` — the number of iterations

The method should return the **last digit of the resulting string** after `n` iterations.

### Example

```text
firstDigit = 1
n = 3

Output: 0