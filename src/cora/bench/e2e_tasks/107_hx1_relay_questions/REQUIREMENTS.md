# Read-only exploration: answer questions about the relay codebase

This task does not change any code. The workspace contains a small message relay
package. Read the code, then answer the five independent questions below.

Write the answers to `ANSWERS.json` in the workspace root. It must be one JSON object
with exactly the keys `q1`, `q2`, `q3`, `q4` and `q5`. No code change is needed.

Questions:

1. How many delivery attempts in total (first attempt plus retries) does the relay make for one message when no setting overrides the default? Answer with an integer in `q1`.
2. Which environment variable overrides the spool directory? Answer with the variable name as a string in `q2`.
3. Which HTTP status code does the API return when a message id is unknown? Answer with an integer in `q3`.
4. What is the name of the function that decides whether a failed delivery is retried? Answer with the function name as a string in `q4`.
5. How many seconds does the relay wait before the third attempt with default settings? Answer with a number in `q5`.
