from __future__ import annotations

from pathlib import Path
import sqlite3

from mcn_ops.store import Store


def test_init_db_creates_expected_tables(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()

    assert {
        "content_packages",
        "publish_jobs",
        "publish_run_logs",
        "tracking_snapshots",
        "ip_roles",
        "collection_tasks",
        "collection_task_roles",
        "collection_runs",
        "collection_candidates",
        "collected_materials",
        "source_authors",
        "source_works",
        "source_observations",
        "material_transcriptions",
        "material_role_matches",
        "material_creations",
        "creation_tasks",
        "creation_stage_runs",
        "creation_material_selections",
        "creation_drafts",
        "creation_delivery_packages",
        "creation_feedback_events",
        "creation_stage_feedback_events",
        "risk_term_observations",
        "creation_learning_updates",
        "ip_role_versions",
        "provider_call_logs",
        "provider_call_cache",
        "schema_migrations",
        "material_understanding_logs",
    }.issubset(set(store.list_tables()))
    assert {
        "douyin_authors",
        "douyin_author_videos",
        "mxnzp_call_logs",
        "mxnzp_call_cache",
    }.isdisjoint(set(store.list_tables()))
    with store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(collected_materials)").fetchall()}
        role_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ip_roles)").fetchall()}
    assert {
        "clean_title",
        "source_role_id",
        "source_work_id",
        "transcription_id",
        "hook_text",
        "core_claim",
        "content_type",
        "oral_script_pattern",
        "risk_level",
    }.issubset(columns)
    assert {
        "caption_text",
        "hashtags_json",
        "duration_ms",
        "cover_url",
        "video_url",
        "audio_url",
        "transcript_text",
    }.isdisjoint(columns)
    assert {
        "confirmation_status",
        "confirmed_at",
        "needs_reconfirm",
        "profile_version",
        "role_baseline",
        "target_audience_json",
        "fit_themes_json",
        "style_anchors_json",
        "persona_packet_json",
    }.issubset(role_columns)


def test_old_ip_roles_schema_migrates_without_data_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "mcn.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE ip_roles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                positioning TEXT NOT NULL DEFAULT '',
                target_directions_json TEXT NOT NULL DEFAULT '[]',
                search_keywords_json TEXT NOT NULL DEFAULT '[]',
                avoid_directions_json TEXT NOT NULL DEFAULT '[]',
                preferred_content_json TEXT NOT NULL DEFAULT '[]',
                forbidden_content_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ip_roles(
                id, name, positioning, target_directions_json, search_keywords_json,
                avoid_directions_json, preferred_content_json, forbidden_content_json,
                enabled, created_at, updated_at
            )
            VALUES ('role_old', '旧角色', '解释型口播', '[]', '["财运"]', '[]', '[]', '[]', 1, 't1', 't1')
            """
        )

    store = Store(db_path)
    store.init_db()
    role = store.get_ip_role("role_old")

    assert role is not None
    assert role["name"] == "旧角色"
    assert role["search_keywords"] == ["财运"]
    assert role["confirmation_status"] == "draft"
    assert role["profile_version"] == 1
    assert role["persona_packet"] == {}


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


def test_ip_role_v2_confirm_versions_and_persona_packet(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()
    role_id = store.upsert_ip_role(
        name="见心说",
        positioning="中年修心口播",
        search_keywords=["修心", "内耗"],
        avoid_directions=["承诺改命"],
        confirmation_status="agent_suggested",
        role_baseline="温和克制的修心型老师",
        life_stage="50岁以上",
        core_temperament="稳定、克制、不表演",
        speaking_posture="像过来人慢慢提醒",
        target_audience={"life_stage": "中年", "pain_points": ["内耗", "执念"]},
        fit_themes=["修心", "放下执念"],
        avoid_themes=["暴富承诺"],
        style_anchors={"opening_style": "一句生活化判断开头"},
        expression_constraints={"allowed_intensity": "medium"},
        forbidden_expressions=["保证发财"],
        typical_topics=["人到中年要学会放下"],
    )
    role = store.get_ip_role(role_id)
    assert role is not None
    assert role["confirmation_status"] == "agent_suggested"
    assert role["persona_packet"]["target_ip"] == "见心说"
    assert role["persona_packet"]["style_anchors"]["opening_style"] == "一句生活化判断开头"

    confirmed = store.confirm_ip_role(role_id, change_reason="首次确认")
    role = confirmed["role"]
    assert role["confirmation_status"] == "confirmed"
    assert role["needs_reconfirm"] is False
    assert role["profile_version"] == 1
    with store.connect() as conn:
        versions = conn.execute("SELECT * FROM ip_role_versions WHERE role_id = ?", (role_id,)).fetchall()
    assert len(versions) == 1
    assert versions[0]["profile_version"] == 1

    store.upsert_ip_role(
        name="见心说",
        positioning="中年修心与关系口播",
        search_keywords=["修心", "内耗"],
    )
    changed = store.get_ip_role(role_id)
    assert changed is not None
    assert changed["confirmation_status"] == "needs_reconfirm"
    assert changed["needs_reconfirm"] is True

    reconfirmed = store.confirm_ip_role(role_id, change_reason="调整定位")
    assert reconfirmed["profile_version"] == 2
    packet = store.build_ip_role_persona_packet(role_id)
    assert packet["target_ip"] == "见心说"
    assert packet["search_keywords"] == ["修心", "内耗"]

    disabled_role_id = store.upsert_ip_role(name="禁用角色", search_keywords=["测试"], enabled=False)
    store.confirm_ip_role(disabled_role_id, change_reason="确认但禁用")
    assert [role["id"] for role in store.list_ip_roles(confirmed_only=True)] == [role_id]


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
            "work_id": "7345678901234567001",
            "title": "口袋放三样，不富人也旺 #财运 #国学智慧",
            "platform_caption": "口袋放三样，不富人也旺 #财运 #国学智慧",
            "transcript_text": "口袋放三样不富人也旺。",
            "source_platform": "douyin",
            "understanding_status": "pending_raw_transcript",
            "material_eligibility": {
                "eligibility_status": "accepted",
                "eligibility_provider": "local-rules",
                "eligibility_version": "material-eligibility-v1",
                "reasons": ["具备知识口播底稿价值。"],
                "content_form": "知识口播",
                "knowledge_core_score": 0.8,
                "oral_script_fit_score": 0.7,
                "ip_fit_score": 0.6,
                "reject_reason": "",
            },
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
    assert material["eligibility_status"] == "accepted"
    assert material["content_form"] == "知识口播"
    assert material["knowledge_core_score"] == 0.8

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
            "work_id": "756",
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
    assert store.get_source_author_by_platform_id("douyin", sec_uid)["id"].startswith("author_")
    assert store.get_source_work_by_platform_id("douyin", "756")["id"] == video_id


def test_provider_call_cache_isolated_by_provider(tmp_path: Path) -> None:
    store = Store(tmp_path / "mcn.sqlite")
    store.init_db()

    store.put_cached_collection_call("search", "same", {"value": "direct"}, provider="direct")
    store.put_cached_collection_call("search", "same", {"value": "other"}, provider="other")

    assert store.get_cached_collection_call("same", provider="direct") == {"value": "direct"}
    assert store.get_cached_collection_call("same", provider="other") == {"value": "other"}
    assert store.get_cached_collection_call("same", provider="missing") is None
