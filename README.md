# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/CyrilLeMat/temper-skills/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                    |    Stmts |     Miss |   Cover |   Missing |
|---------------------------------------- | -------: | -------: | ------: | --------: |
| temper\_skills/\_\_init\_\_.py          |       10 |        0 |    100% |           |
| temper\_skills/audit.py                 |       86 |        0 |    100% |           |
| temper\_skills/audit\_report.py         |       98 |        2 |     98% |   216-217 |
| temper\_skills/backends/\_\_init\_\_.py |       25 |        1 |     96% |        17 |
| temper\_skills/backends/agent\_cli.py   |       95 |        0 |    100% |           |
| temper\_skills/backends/api.py          |       64 |        5 |     92% |     38-43 |
| temper\_skills/backends/base.py         |       17 |        0 |    100% |           |
| temper\_skills/cli.py                   |      472 |      108 |     77% |65, 73, 86-90, 92-93, 114-120, 188-190, 201, 207-211, 241-242, 272-274, 287, 334-339, 348-353, 362-368, 375, 386-396, 414-416, 484-521, 588-590, 605, 608-636, 684-685, 717-718, 809, 830-839, 845-847, 962-964, 1003-1005, 1012-1020, 1037-1038, 1061-1063, 1088-1094, 1098 |
| temper\_skills/decompose.py             |       30 |        0 |    100% |           |
| temper\_skills/distill.py               |      326 |       10 |     97% |86, 256, 285, 658, 764-765, 777-778, 851, 863 |
| temper\_skills/export\_schema.py        |       31 |        0 |    100% |           |
| temper\_skills/export\_skill.py         |       48 |        3 |     94% |102-110, 145 |
| temper\_skills/export\_tree.py          |      118 |        2 |     98% |  159, 309 |
| temper\_skills/incremental.py           |       53 |        0 |    100% |           |
| temper\_skills/ingest.py                |       38 |        0 |    100% |           |
| temper\_skills/pipelines.py             |       74 |        1 |     99% |        40 |
| temper\_skills/schemas.py               |       34 |        0 |    100% |           |
| temper\_skills/skill\_docs.py           |       55 |        5 |     91% |129-131, 136-137 |
| temper\_skills/skill\_render.py         |      142 |        7 |     95% |202, 275, 323, 330-336, 343, 358 |
| temper\_skills/sources.py               |       33 |        0 |    100% |           |
| temper\_skills/tree.py                  |       61 |        0 |    100% |           |
| temper\_skills/update\_validation.py    |       54 |        0 |    100% |           |
| temper\_skills/validate.py              |       65 |        0 |    100% |           |
| temper\_skills/validation\_case.py      |       38 |        1 |     97% |        76 |
| temper\_skills/vendor\_scripts.py       |       28 |        0 |    100% |           |
| **TOTAL**                               | **2095** |  **145** | **93%** |           |


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