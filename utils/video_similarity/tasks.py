"""Persistent, single-writer background tasks for the local workspace."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import threading
import time
import uuid


def now():
    return datetime.now().isoformat(timespec='seconds')


class TaskBusy(RuntimeError):
    pass


class TaskFailure(RuntimeError):
    """A failed stage can still have completed file changes to report."""
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


class TaskManager:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.items = []
        self.active = None
        self.last_save = 0
        self.server_id = uuid.uuid4().hex
        if self.path.exists():
            self.items = json.loads(self.path.read_text(encoding='utf-8'))
        for item in self.items:
            if item['state'] == 'running':
                item.update(state='interrupted', finished_at=now(),
                            message='服务曾中断。请核对已完成的文件，再重新发起操作。')
        self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.items, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self.last_save = time.monotonic()

    @contextmanager
    def exclusive(self):
        """Serialize short mutations with task admission (including other tabs)."""
        with self.lock:
            if self.active:
                raise TaskBusy('已有后台任务正在运行，请完成后再操作。')
            yield

    def start(self, kind, label, operation):
        with self.exclusive():
            item = dict(id=uuid.uuid4().hex, kind=kind, label=label, state='running',
                        started_at=now(), finished_at=None, stage='准备中',
                        message='正在准备任务', completed=0, total=None, result=None)
            self.items = [item, *self.items[:19]]
            self.active = item['id']
            self._save()
            initial = deepcopy(item)
            threading.Thread(target=self._run, args=(item, operation), daemon=True,
                             name='workspace-' + kind).start()
            return initial

    def _run(self, item, operation):
        def progress(stage, completed=0, total=None, message=''):
            with self.lock:
                item.update(stage=stage, completed=completed, total=total, message=message or stage)
                if time.monotonic() - self.last_save > 0.5:
                    self._save()
        try:
            result = operation(progress) or {}
            errors = result.get('errors', [])
            state = 'partial' if errors or result.get('success') is False else 'complete'
            with self.lock:
                item.update(state=state, result=result,
                            message='任务完成，有部分项目需要处理' if state == 'partial' else '任务完成')
        except Exception as exc:
            with self.lock:
                item.update(state='failed', message=str(exc), error=str(exc),
                            result=getattr(exc, 'result', None))
        finally:
            with self.lock:
                item['finished_at'] = now()
                self.active = None
                self._save()

    def clear_history(self):
        """Remove persisted history only, without touching reports or files."""
        with self.exclusive():
            previous = self.items
            self.items = []
            try:
                self._save()
            except Exception:
                self.items = previous
                raise
            return len(previous)

    def snapshot(self, task_id=None):
        with self.lock:
            if task_id:
                return deepcopy(next((item for item in self.items if item['id'] == task_id), None))
            return dict(server_id=self.server_id, active_id=self.active,
                        tasks=[{key: deepcopy(value) for key, value in item.items() if key != 'result'}
                               for item in self.items])
