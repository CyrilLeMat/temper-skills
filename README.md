# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/CyrilLeMat/temper-skills/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                    |    Stmts |     Miss |   Cover |   Missing |
|---------------------------------------- | -------: | -------: | ------: | --------: |
| temper\_skills/\_\_init\_\_.py          |       10 |        0 |    100% |           |
| temper\_skills/audit.py                 |       86 |        0 |    100% |           |
| temper\_skills/audit\_report.py         |       98 |        2 |     98% |   189-190 |
| temper\_skills/backends/\_\_init\_\_.py |       25 |        1 |     96% |        17 |
| temper\_skills/backends/agent\_cli.py   |       95 |        0 |    100% |           |
| temper\_skills/backends/api.py          |       50 |        0 |    100% |           |
| temper\_skills/backends/base.py         |       17 |        0 |    100% |           |
| temper\_skills/cli.py                   |      471 |      108 |     77% |61, 69, 82-86, 88-89, 108-112, 167-169, 177, 181-183, 210-211, 227-229, 242, 282-285, 294-297, 306-310, 317, 326-334, 347-349, 394-423, 480-482, 496, 499-512, 545-546, 577-578, 651, 663-666, 670-672, 740-742, 767-769, 776-778, 795-796, 810-812, 834-840, 844 |
| temper\_skills/decompose.py             |       30 |        0 |    100% |           |
| temper\_skills/distill.py               |      325 |       10 |     97% |75, 236, 262, 588, 688-689, 700-701, 765, 777 |
| temper\_skills/export\_schema.py        |       31 |        0 |    100% |           |
| temper\_skills/export\_skill.py         |       48 |        3 |     94% |92-98, 128 |
| temper\_skills/export\_tree.py          |      118 |        2 |     98% |  152, 292 |
| temper\_skills/incremental.py           |       53 |        0 |    100% |           |
| temper\_skills/ingest.py                |       38 |        0 |    100% |           |
| temper\_skills/pipelines.py             |       72 |        0 |    100% |           |
| temper\_skills/schemas.py               |       34 |        0 |    100% |           |
| temper\_skills/skill\_docs.py           |       50 |        5 |     90% |108-110, 115-116 |
| temper\_skills/skill\_render.py         |      142 |        7 |     95% |193, 258, 292, 299-302, 309, 319 |
| temper\_skills/sources.py               |       33 |        0 |    100% |           |
| temper\_skills/tree.py                  |       60 |        0 |    100% |           |
| temper\_skills/update\_validation.py    |       54 |        0 |    100% |           |
| temper\_skills/validate.py              |       65 |        0 |    100% |           |
| temper\_skills/validation\_case.py      |       38 |        1 |     97% |        77 |
| temper\_skills/vendor\_scripts.py       |       28 |        0 |    100% |           |
| **TOTAL**                               | **2071** |  **139** | **93%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/CyrilLeMat/temper-skills/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/CyrilLeMat/temper-skills/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CyrilLeMat/temper-skills/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/CyrilLeMat/temper-skills/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FCyrilLeMat%2Ftemper-skills%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/CyrilLeMat/temper-skills/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.