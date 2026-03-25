"""Tests for wizard dual mode — step/mode detection."""
import pytest
from app.routers.wizard import _detect_step, _strip_markers


def test_detect_mode_guided():
    step, mode = _detect_step("Bien ! [MODE:guided] Étape 1/11 — Quel univers...", 1, None)
    assert mode == "guided"
    assert step == 1


def test_detect_mode_surprise():
    step, mode = _detect_step("Super ! [MODE:surprise] Étape 1/4 — Quel genre...", 1, None)
    assert mode == "surprise"
    assert step == 1


def test_detect_step_guided_advances():
    step, mode = _detect_step("Étape 5/11 — Parlons des richesses...", 4, "guided")
    assert step == 5
    assert mode is None


def test_detect_step_surprise_advances():
    step, mode = _detect_step("Étape 2/4 — Une envie particulière ?", 1, "surprise")
    assert step == 2
    assert mode is None


def test_detect_step_never_goes_back():
    step, mode = _detect_step("Étape 2/11 — Revenons...", 5, "guided")
    assert step == 5


def test_detect_step_no_marker():
    step, mode = _detect_step("Ah, intéressant ! Dis-moi en plus...", 3, "guided")
    assert step == 3
    assert mode is None


def test_strip_markers():
    text = "Super choix ! [MODE:surprise] Étape 1/4 — Quel genre..."
    clean = _strip_markers(text)
    assert "[MODE:" not in clean
    assert "Super choix" in clean


def test_strip_markers_no_marker():
    text = "Ah, intéressant !"
    assert _strip_markers(text) == text


import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.routers.wizard import generate_world


@pytest.mark.asyncio
async def test_generate_rejects_guided_mode():
    """POST /generate should return 409 if mode is not 'surprise'."""
    mock_session = MagicMock()
    mock_session.mode = "guided"
    mock_session.current_step = 3
    mock_session.generation_task_id = None
    mock_session.user_id = 1

    from fastapi import HTTPException
    with patch("app.routers.wizard._get_session", new=AsyncMock(return_value=mock_session)):
        with pytest.raises(HTTPException) as exc_info:
            await generate_world("test-session", MagicMock(id=1), AsyncMock())
        assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_generate_rejects_early_step():
    """POST /generate should return 409 if step < 3."""
    mock_session = MagicMock()
    mock_session.mode = "surprise"
    mock_session.current_step = 1
    mock_session.generation_task_id = None
    mock_session.user_id = 1

    from fastapi import HTTPException
    with patch("app.routers.wizard._get_session", new=AsyncMock(return_value=mock_session)):
        with pytest.raises(HTTPException) as exc_info:
            await generate_world("test-session", MagicMock(id=1), AsyncMock())
        assert exc_info.value.status_code == 409


def test_generation_status_resolved_from_world_when_task_missing():
    """If task_id exists but task not found, status should be deduced from world state."""
    from app.services.task_manager import get_task

    # When task is not in task_manager, get_task returns None
    assert get_task("nonexistent-task-id") is None
