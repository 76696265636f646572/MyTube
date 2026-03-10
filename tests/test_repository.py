from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository


def test_queue_ordering_and_reorder(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path}/repo.db"
    repo = Repository(db_url)
    repo.init_db()

    created = repo.enqueue_items(
        [
            NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="a"),
            NewQueueItem(source_url="u2", normalized_url="u2", source_type="video", title="b"),
            NewQueueItem(source_url="u3", normalized_url="u3", source_type="video", title="c"),
        ]
    )
    assert [x.queue_position for x in created] == [1, 2, 3]

    assert repo.reorder_item(created[2].id, 0) is True
    queue = repo.list_queue()
    assert [x.title for x in queue if x.status == QueueStatus.queued] == ["c", "a", "b"]

    next_item = repo.dequeue_next()
    assert next_item is not None
    assert next_item.title == "c"
    assert next_item.status == QueueStatus.playing


def test_replace_queued_items_marks_old_items_removed(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path}/repo_replace.db"
    repo = Repository(db_url)
    repo.init_db()

    first_batch = repo.enqueue_items(
        [
            NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="a"),
            NewQueueItem(source_url="u2", normalized_url="u2", source_type="video", title="b"),
        ]
    )
    repo.dequeue_next()

    replacement = repo.replace_queued_items(
        [NewQueueItem(source_url="u3", normalized_url="u3", source_type="video", title="c")]
    )

    assert len(replacement) == 1
    queue = repo.list_queue()
    assert len([item for item in queue if item.status == QueueStatus.playing]) == 1
    assert [item.title for item in queue if item.status == QueueStatus.queued] == ["c"]

    removed_status = repo.get_item(first_batch[1].id)
    assert removed_status is not None
    assert removed_status.status == QueueStatus.removed


def test_dequeue_next_demotes_previous_playing_item(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path}/repo_single_playing.db"
    repo = Repository(db_url)
    repo.init_db()

    created = repo.enqueue_items(
        [
            NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="a"),
            NewQueueItem(source_url="u2", normalized_url="u2", source_type="video", title="b"),
        ]
    )

    first_item = repo.dequeue_next()
    assert first_item is not None
    assert first_item.id == created[0].id

    second_item = repo.dequeue_next()
    assert second_item is not None
    assert second_item.id == created[1].id
    assert second_item.status == QueueStatus.playing

    refreshed_first = repo.get_item(created[0].id)
    assert refreshed_first is not None
    assert refreshed_first.status == QueueStatus.skipped


def test_list_queue_repairs_multiple_playing_rows(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path}/repo_repair_playing.db"
    repo = Repository(db_url)
    repo.init_db()

    created = repo.enqueue_items(
        [
            NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="a"),
            NewQueueItem(source_url="u2", normalized_url="u2", source_type="video", title="b"),
            NewQueueItem(source_url="u3", normalized_url="u3", source_type="video", title="c"),
        ]
    )

    repo.dequeue_next()
    with repo.session() as session:
        second = session.get(type(created[1]), created[1].id)
        assert second is not None
        second.status = QueueStatus.playing

    queue = repo.list_queue()

    playing_items = [item for item in queue if item.status == QueueStatus.playing]
    assert len(playing_items) == 1
    assert playing_items[0].id == created[1].id

    refreshed_first = repo.get_item(created[0].id)
    assert refreshed_first is not None
    assert refreshed_first.status == QueueStatus.skipped


def test_history_preserves_thumbnail_url(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path}/repo_history.db"
    repo = Repository(db_url)
    repo.init_db()

    created = repo.enqueue_items(
        [
            NewQueueItem(
                source_url="https://www.youtube.com/watch?v=abc123",
                normalized_url="https://www.youtube.com/watch?v=abc123",
                source_type="video",
                title="thumb track",
                thumbnail_url="https://i.ytimg.com/vi/abc123/hqdefault.jpg",
            )
        ]
    )
    item = repo.dequeue_next()

    assert item is not None

    repo.mark_playback_finished(created[0].id, QueueStatus.completed)

    history = repo.list_history()

    assert len(history) == 1
    assert history[0].thumbnail_url == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
