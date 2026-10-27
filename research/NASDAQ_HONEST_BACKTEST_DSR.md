# NASDAQ DSR trial-selection guard — research only

Library: MIT [honest-backtest](https://github.com/jersgcodes/honest-backtest) pinned at 7f63e3228d368f1d86b7ee50651f0236e16de32c. Numerically tests that adjusting for more attempted strategies lowers Deflated Sharpe confidence versus a naive Probabilistic Sharpe; checks heavy-tail sensitivity, missing trial history and invalid variance.

Not connected to production AL/STOP/target, not an ML predictor, not a fill simulator. Its DSR does not make 27 October AL profitable. Effective N can differ with serial correlation; this synthetic witness cannot claim historical statistical significance. An actual NASDAQ risk study needs a complete trial registry, honest point-in-time data, OOS validation, costs, and correct sample-autocorrelation accounting.

The existing 477 stock scanner, one private sheet, one ChatGPT task, push and 15-day episodes remain untouched.