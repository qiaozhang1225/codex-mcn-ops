"""Douyin Web endpoint constants.

The endpoint inventory was checked against Evil0ctal/Douyin_TikTok_Download_API,
an Apache-2.0 project. The constants below are a small, independently adapted
subset; see THIRD_PARTY_NOTICES.md in this directory.
"""

DOUYIN_HOME = "https://www.douyin.com"
DETAIL = f"{DOUYIN_HOME}/aweme/v1/web/aweme/detail/"
USER_POST = f"{DOUYIN_HOME}/aweme/v1/web/aweme/post/"
VIDEO_SEARCH = f"{DOUYIN_HOME}/aweme/v1/web/search/item/"
USER_SEARCH = f"{DOUYIN_HOME}/aweme/v1/web/discover/search/"
USER_INFO = f"{DOUYIN_HOME}/aweme/v1/web/user/profile/other/"

METHOD_ENDPOINTS = {
    "detail": DETAIL,
    "detail_v3": DETAIL,
    "detail_v4": DETAIL,
    "user_post": USER_POST,
    "video_search": VIDEO_SEARCH,
    "user_search": USER_SEARCH,
    "user_info": USER_INFO,
    "user_info_dy_id": USER_INFO,
}
