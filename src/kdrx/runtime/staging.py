"""Private attempt workspaces for trusted handlers; immutable publication inputs."""

from __future__ import annotations

from kdrx.security import safe_join, has_symlink_component
from kdrx.schemas.versioning import validate_component
from kdrx.state import RunState, hash_bytes


class AttemptWorkspace(RunState):
    """Failed or fenced attempts never write into the published run tree.

    This filesystem boundary is enforced for kernel APIs and checked after
    trusted Python execution. It is not an OS sandbox for hostile code.
    """

    def __init__(
        self, parent: RunState, attempt_id: str, outputs: list[str], inputs: list[str]
    ):
        super().__init__(parent.root, parent.run_id)
        self.parent = parent
        self._store_instance = parent.store
        self.run_dir = safe_join(
            parent.root, f".staging/{parent.run_id}/{validate_component(attempt_id)}"
        )
        if has_symlink_component(self.run_dir):
            raise ValueError("staging cannot traverse a link or junction")
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.outputs = {self._relative(path) for path in outputs}
        self.output_keys = {path.casefold() for path in self.outputs}
        self.input_hashes: dict[str, str] = {}
        self.staged_events: list[dict] = []
        parent.flush_exports()
        for relative in sorted(set(inputs)):
            relative = self._relative(relative)
            if relative.casefold() in self.output_keys:
                raise ValueError(f"task cannot overwrite its input: {relative}")
            data = parent._resolve(relative).read_bytes()
            path = self._resolve(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(path, data)
            self.input_hashes[relative] = hash_bytes(data)

    def _relative(self, path: str) -> str:
        return self._resolve(path).relative_to(self.run_dir).as_posix()

    def write_text(self, rel_path: str, content: str):
        if self._relative(rel_path).casefold() not in self.output_keys:
            raise ValueError(f"undeclared attempt output: {rel_path}")
        return super().write_text(rel_path, content)

    def append_event(self, event: dict) -> None:
        self.staged_events.append(dict(event))

    def flush_exports(self) -> None:
        raise ValueError("attempt cannot publish exports")

    def save_manifest(self, manifest) -> None:
        raise ValueError("attempt cannot mutate the run checkpoint")

    def commit_bundle(self, manifest, files) -> None:
        raise ValueError("attempt cannot publish a bundle")

    def validate_boundary(self) -> None:
        current = self.snapshot_hashes()
        if len({path.casefold() for path in current}) != len(current):
            raise ValueError("attempt contains equivalent path aliases")
        unexpected = set(current) - self.outputs - set(self.input_hashes)
        if unexpected:
            raise ValueError(f"undeclared attempt files: {sorted(unexpected)}")
        for relative, digest in self.input_hashes.items():
            if current.get(relative) != digest:
                raise ValueError(f"attempt modified its input: {relative}")
            if hash_bytes(self.parent._resolve(relative).read_bytes()) != digest:
                raise ValueError(f"input changed during attempt: {relative}")
