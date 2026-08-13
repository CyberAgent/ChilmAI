# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/CyberAgent/ChilmAI/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                     |    Stmts |     Miss |     Cover |   Missing |
|--------------------------------------------------------- | -------: | -------: | --------: | --------: |
| apps/\_\_init\_\_.py                                     |        0 |        0 |    100.0% |           |
| apps/api/main.py                                         |      435 |       44 |     89.9% |63, 75, 107, 110, 113-115, 196, 246-247, 256, 374, 625, 627, 686, 728-729, 855-856, 982, 984-986, 1012-1036, 1090-1091, 1113 |
| apps/version.py                                          |       13 |        3 |     76.9% |   6-8, 16 |
| chilmai/\_\_init\_\_.py                                  |        0 |        0 |    100.0% |           |
| chilmai/algorithm/\_\_init\_\_.py                        |        0 |        0 |    100.0% |           |
| chilmai/algorithm/cp\_use\_transfer/CP\_agents.py        |      162 |       42 |     74.1% |35, 38, 97, 100, 132, 148-156, 166-173, 199-211, 260-275, 305, 308, 351, 363 |
| chilmai/algorithm/cp\_use\_transfer/CP\_algo.py          |      138 |        1 |     99.3% |       294 |
| chilmai/algorithm/cp\_use\_transfer/\_\_init\_\_.py      |        0 |        0 |    100.0% |           |
| chilmai/algorithm/cp\_use\_transfer/helper\_functions.py |      199 |       24 |     87.9% |26, 57, 119, 178-183, 203, 208, 230-247, 252 |
| chilmai/constants.py                                     |        1 |        0 |    100.0% |           |
| chilmai/generic/\_\_init\_\_.py                          |        4 |        0 |    100.0% |           |
| chilmai/generic/column\_mapper.py                        |      105 |        6 |     94.3% |70, 92, 95, 97, 110-111 |
| chilmai/generic/config.py                                |      183 |       21 |     88.5% |65, 69, 80, 84, 87, 89, 97, 129-130, 135, 143, 146-147, 150, 153, 196, 238, 255, 257, 259, 273 |
| chilmai/generic/dict\_builder.py                         |      114 |        4 |     96.5% |59-60, 98-99 |
| chilmai/generic/error\_codes.py                          |       48 |        0 |    100.0% |           |
| chilmai/generic/family\_pref\_builder.py                 |      149 |       12 |     91.9% |81, 115-116, 123, 127, 134-135, 145, 177-178, 198-199 |
| chilmai/generic/matcher.py                               |      173 |        3 |     98.3% |   229-233 |
| chilmai/generic/parser.py                                |      158 |       11 |     93.0% |136, 149, 190, 252, 255, 277, 279, 284, 292, 294, 299 |
| chilmai/generic/preprocessor.py                          |       27 |        0 |    100.0% |           |
| chilmai/generic/service.py                               |      131 |        4 |     96.9% |60-61, 194, 236 |
| chilmai/generic/sibling\_pref\_patterns.py               |       96 |        1 |     99.0% |        42 |
| chilmai/generic/validator.py                             |      289 |       19 |     93.4% |66, 130-131, 173-174, 231-239, 535-542, 544-551, 557-559, 612, 618, 643-644 |
| **TOTAL**                                                | **2425** |  **195** | **92.0%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/CyberAgent/ChilmAI/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/CyberAgent/ChilmAI/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CyberAgent/ChilmAI/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/CyberAgent/ChilmAI/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FCyberAgent%2FChilmAI%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/CyberAgent/ChilmAI/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.