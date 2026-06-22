from __future__ import annotations

from pathlib import Path

from mcn_ops.store import Store


def test_init_db_creates_expected_tables(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()

    assert {
        "ip_profiles",
        "content_packages",
        "publish_jobs",
        "android_devices",
        "app_accounts",
        "publish_run_logs",
        "tracking_snapshots",
        "ip_roles",
        "collection_tasks",
        "collection_task_roles",
        "collection_runs",
        "collection_candidates",
        "collected_materials",
        "douyin_authors",
        "douyin_author_videos",
        "material_role_matches",
        "material_creations",
        "mxnzp_call_logs",
        "mxnzp_call_cache",
        "material_understanding_logs",
    }.issubset(set(store.list_tables()))
    with store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(collected_materials)").fetchall()}
    assert {
        "clean_title",
        "source_role_id",
        "caption_text",
        "hashtags_json",
        "hook_text",
        "core_claim",
        "content_type",
        "oral_script_pattern",
        "risk_level",
        "duration_ms",
        "cover_url",
        "video_url",
        "audio_url",
    }.issubset(columns)


def test_create_content_and_publish_job(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    content_id = store.create_content_package(
        title="title",
        body="body",
        media_paths=["/tmp/video.mp4"],
        cover_path="/tmp/cover.jpg",
        hashtags=["topic"],
    )

    job_id = store.create_publish_job(content_id=content_id, platform="douyin", device_serial="device-1")
    job, content = store.get_job_with_content(job_id)

    assert job["platform"] == "douyin"
    assert job["stop_before_submit"] == 1
    assert content["title"] == "title"


def test_role_and_material_promotion(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="知识型老师",
        positioning="解释型口播",
        search_keywords=["知识型口播"],
    )
    run_id = store.create_collection_run(
        task_id=None,
        role_id=role_id,
        topic="知识型口播",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mock",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "role_id": role_id,
            "source_link": "mock://1",
            "title": "知识型口播素材",
            "platform_caption": "caption",
            "transcript_text": "知识型口播要先有观点。",
            "source_platform": "mock",
            "public_metrics": {"likes": 10},
        },
        material_understanding={
            "topic_summary": "知识型口播要先有观点。",
            "understanding_provider": "codex",
            "understanding_model": "gpt-5.5",
        },
        raw={},
    )

    content_id = store.promote_material_to_content_package(material_id, platform="douyin")
    content = store.get_content_package(content_id)
    material = store.get_collected_material(material_id)

    assert material is not None
    assert material["status"] == "collected"
    assert material["source_role_id"] == role_id
    assert content["title"] == "知识型口播素材"
    creations = store.list_material_creations(material_id=material_id, role_id=role_id)
    assert len(creations) == 1
    assert creations[0]["content_package_id"] == content_id


def test_material_v2_promoted_columns_and_pending_summary(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    run_id = store.create_collection_run(
        task_id=None,
        role_id=None,
        topic="财运",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mxnzp",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "source_link": "https://example.com/video",
            "title": "口袋放三样，不富人也旺 #财运 #国学智慧",
            "platform_caption": "口袋放三样，不富人也旺 #财运 #国学智慧",
            "transcript_text": "口袋放三样不富人也旺。",
            "source_platform": "douyin",
            "understanding_status": "pending_raw_transcript",
        },
        material_understanding={
            "topic_summary": "口袋放三样不富人也旺。",
            "status": "pending_deep_understanding",
        },
        raw={
            "video_to_text_v2_result": {
                "raw": {
                    "data": {
                        "douyinInfo": {
                            "postTime": "2026-01-01 10:00:00",
                            "videoDuration": 97801,
                            "cover": "https://example.com/cover.jpg",
                            "videoUrl": "https://example.com/video.mp4",
                            "audioUrl": "https://example.com/audio.mp3",
                        }
                    }
                }
            }
        },
    )
    material = store.get_collected_material(material_id)

    assert material is not None
    assert material["clean_title"] == "口袋放三样，不富人也旺"
    assert material["caption_text"] == "口袋放三样，不富人也旺"
    assert material["hashtags"] == ["财运", "国学智慧"]
    assert material["summary_text"] is None
    assert material["duration_ms"] == 97801
    assert material["cover_url"] == "https://example.com/cover.jpg"

    store.update_material_understanding(
        material_id,
        understanding={
            "topic_summary": "讲口袋随身物件如何提供心理暗示。",
            "hook": "口袋放三样",
            "core_claim": "民俗物件的价值主要是心理暗示。",
            "content_structure": ["问题开头", "三点方法", "理性收束"],
            "key_points": ["六枚硬币", "盐", "七粒米"],
            "content_type": "方法清单",
            "oral_script_pattern": "问题开头-三点方法-理性收束",
            "audience": "关注财运话题的人群",
            "emotion_trigger": "方法感",
            "risk_level": "medium",
            "rewrite_angles": ["改写成心理暗示角度"],
            "risk_notes": ["避免承诺发财"],
            "usable_quotes": ["关键是心理暗示"],
            "recommended_platforms": ["douyin"],
            "role_fit_notes": "适合玄学口播",
            "next_collection_keywords": ["旺自己"],
        },
        provider="codex",
        model="gpt-5.5",
    )
    updated = store.get_collected_material(material_id)
    assert updated is not None
    assert updated["summary_text"] == "讲口袋随身物件如何提供心理暗示。"
    assert updated["content_type"] == "方法清单"
    assert updated["oral_script_pattern"] == "问题开头-三点方法-理性收束"
    assert updated["key_points"] == ["六枚硬币", "盐", "七粒米"]


def test_material_can_match_multiple_roles_and_track_role_creation(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_a = store.upsert_ip_role(name="国学老师", search_keywords=["财运"])
    role_b = store.upsert_ip_role(name="女性成长", search_keywords=["旺自己"])
    run_id = store.create_collection_run(
        task_id=None,
        role_id=None,
        topic="财运",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mock",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "source_link": "mock://multi-role",
            "title": "财运和旺自己的口播",
            "platform_caption": "财运和旺自己的口播 #财运",
            "transcript_text": "财运和旺自己都可以从认知和行动习惯展开。",
            "source_platform": "mock",
        },
        material_understanding={"topic_summary": "财运和旺自己都可以从认知和行动习惯展开。"},
        raw={},
    )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_a,
        task_id=None,
        fit_score=0.91,
        decision="accepted",
        reasons=["命中财运"],
    )
    store.insert_material_role_match(
        material_id=material_id,
        role_id=role_b,
        task_id=None,
        fit_score=0.88,
        decision="accepted",
        reasons=["命中旺自己"],
    )
    content_id = store.promote_material_to_content_package(
        material_id,
        platform="douyin",
        role_id=role_b,
        rewrite_angle="女性成长角度",
    )

    assert [item["id"] for item in store.list_collected_materials(role_id=role_a)] == [material_id]
    assert [item["id"] for item in store.list_collected_materials(role_id=role_b)] == [material_id]
    creations_a = store.list_material_creations(material_id=material_id, role_id=role_a)
    creations_b = store.list_material_creations(material_id=material_id, role_id=role_b)
    assert creations_a == []
    assert creations_b[0]["content_package_id"] == content_id
    assert creations_b[0]["rewrite_angle"] == "女性成长角度"


def test_douyin_author_profile_and_video_storage(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    run_id = store.create_collection_run(
        task_id=None,
        role_id=None,
        topic="旺自己",
        target_count=1,
        like_floor=1,
        super_like_threshold=100,
        tool_provider="mxnzp",
    )
    material_id = store.insert_collected_material(
        run_id=run_id,
        source_package={
            "source_link": "https://example.com/video",
            "title": "八个旺自己的秘密 #女性成长",
            "platform_caption": "八个旺自己的秘密 #女性成长",
            "transcript_text": "旺自己要先稳住能量。",
            "source_platform": "douyin",
        },
        material_understanding={"topic_summary": "旺自己要先稳住能量。"},
        raw={},
    )
    sec_uid = store.upsert_douyin_author(
        {
            "sec_uid": "sec_1",
            "uid": "uid_1",
            "douyin_id": "626720886",
            "nickname": "娜说智慧",
            "raw": {
                "signature": "专注女性成长",
                "follower_count": 51524,
                "aweme_count": 507,
                "avatar_thumb": {"url_list": ["https://example.com/avatar.jpg"]},
            },
        },
        source_material_id=material_id,
        source_work_id="756",
    )
    video_id = store.upsert_douyin_author_video(
        sec_uid,
        {
            "work_id": "756",
            "source_url": "https://example.com/video",
            "caption": "八个旺自己的秘密 #女性成长",
            "duration_ms": 257700,
            "metrics": {"digg_count": 26144},
        },
        source_material_id=material_id,
    )
    store.update_collected_material_author(
        material_id,
        author_name="娜说智慧",
        author_sec_uid=sec_uid,
        author_profile_url="https://www.iesdouyin.com/share/user/sec_1",
        author_douyin_id="626720886",
        work_id="756",
    )

    author = store.get_douyin_author(sec_uid)
    material = store.get_collected_material(material_id)
    videos = store.list_douyin_author_videos(sec_uid)
    assert author is not None
    assert author["nickname"] == "娜说智慧"
    assert author["follower_count"] == 51524
    assert author["avatar_url"] == "https://example.com/avatar.jpg"
    assert material is not None
    assert material["author_sec_uid"] == sec_uid
    assert videos[0]["id"] == video_id
    assert videos[0]["hashtags"] == ["女性成长"]
