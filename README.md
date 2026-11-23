# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/antoiba86/ha-home-keeper-games/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|----------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| custom\_components/home\_keeper\_games/\_\_init\_\_.py     |       73 |        0 |        6 |        1 |     99% | 118-\>123 |
| custom\_components/home\_keeper\_games/api\_surface.py     |       91 |        0 |        0 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/backend\_i18n.py    |       58 |        3 |       12 |        1 |     94% | 65-66, 88 |
| custom\_components/home\_keeper\_games/card.py             |       79 |       19 |       28 |        6 |     73% |59, 80-82, 84-85, 89, 102, 115, 122-133, 137, 157-158 |
| custom\_components/home\_keeper\_games/card\_resource.py   |       29 |        0 |        2 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/config\_flow.py     |       43 |        0 |       10 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/const.py            |       74 |        0 |        0 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/coordinator.py      |       41 |        0 |        6 |        1 |     98% |   79-\>77 |
| custom\_components/home\_keeper\_games/covers.py           |      210 |       20 |       62 |       10 |     89% |87, 97, 107, 140, 155-157, 169-\>exit, 189, 216, 219, 225-227, 247-248, 275-276, 325, 334, 382 |
| custom\_components/home\_keeper\_games/csv\_io.py          |      294 |        1 |       90 |        0 |     99% |       190 |
| custom\_components/home\_keeper\_games/diagnostics.py      |       10 |        0 |        0 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/entity.py           |       50 |        1 |        8 |        1 |     97% |        62 |
| custom\_components/home\_keeper\_games/events.py           |       40 |        0 |        0 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/frontend\_assets.py |       17 |        0 |        2 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/home\_keeper.py     |      135 |        5 |       34 |        2 |     96% |144, 259, 277-279 |
| custom\_components/home\_keeper\_games/import\_export.py   |      510 |        2 |      196 |        3 |     99% |319-\>317, 572-575, 713-\>715 |
| custom\_components/home\_keeper\_games/loan\_sync.py       |      131 |       15 |       50 |       13 |     85% |79-\>exit, 97, 112, 121-123, 128-\>131, 140, 147, 151, 168-\>148, 181, 185-186, 198, 205, 212, 215 |
| custom\_components/home\_keeper\_games/loan\_tasks.py      |      104 |        0 |       36 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/models.py           |      458 |        0 |      260 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/people.py           |       36 |        3 |       10 |        3 |     87% |40, 56, 63 |
| custom\_components/home\_keeper\_games/projections.py      |      178 |        1 |       84 |        1 |     99% |       342 |
| custom\_components/home\_keeper\_games/sensor.py           |       74 |        0 |        0 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/services.py         |      413 |        8 |      108 |        9 |     97% |343-344, 348-\>347, 352, 453, 559, 605, 708-\>710, 812, 841 |
| custom\_components/home\_keeper\_games/store.py            |      485 |       33 |      140 |       27 |     90% |81, 118-\>exit, 134-135, 218, 242-\>244, 246, 271-\>273, 275, 290, 374, 386-\>388, 394, 414, 425-\>exit, 453, 533-537, 581, 626-\>640, 691, 699, 701-\>703, 756, 758-\>764, 765-768, 770, 800, 819-\>817, 825-\>822, 838-846 |
| custom\_components/home\_keeper\_games/todo.py             |       69 |        9 |       14 |        3 |     86% |109, 126-127, 133, 138-139, 148, 151-152 |
| custom\_components/home\_keeper\_games/websocket\_api.py   |       79 |        6 |       12 |        2 |     91% |101-108, 124-125, 152-153 |
| custom\_components/home\_keeper\_games/wishlist.py         |      117 |        0 |       44 |        0 |    100% |           |
| custom\_components/home\_keeper\_games/wishlist\_sync.py   |      103 |        7 |       28 |        3 |     92% |72-\>exit, 92-\>exit, 98, 108-110, 128-130 |
| **TOTAL**                                                  | **4001** |  **133** | **1242** |   **86** | **96%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/antoiba86/ha-home-keeper-games/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/antoiba86/ha-home-keeper-games/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/antoiba86/ha-home-keeper-games/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/antoiba86/ha-home-keeper-games/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fantoiba86%2Fha-home-keeper-games%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/antoiba86/ha-home-keeper-games/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.