#!/usr/bin/env python3
import pathlib
import sys
import textwrap


KERNEL_SERVER = pathlib.Path("/app/kernel_server.py")


EXECUTE_MODELS = '''
from typing import Any


class KernelExecuteRequest(BaseModel):
    """Kernel execution request model"""

    code: str
    timeout: float = 30
    restart: bool = False


class KernelExecuteResponse(BaseModel):
    """Kernel execution response model"""

    success: bool
    output: Any = ""
    error: Optional[str] = None
    images: list[str] = []
'''


EXECUTE_ROUTE = '''

@app.post("/kernel/execute", response_model=KernelExecuteResponse)
async def execute_kernel(request: KernelExecuteRequest):
    """Execute code inside the sandbox kernel through fixed HTTP port 8888."""
    global kernel_instance
    if not kernel_instance:
        raise HTTPException(status_code=503, detail="Kernel not initialized")

    try:
        if request.restart:
            reset_result = kernel_instance.reset_kernel()
            if not reset_result.get("success"):
                raise HTTPException(
                    status_code=500,
                    detail=reset_result.get("message", "Failed to reset kernel"),
                )

        result = kernel_instance.execute(request.code, timeout=request.timeout)
        return KernelExecuteResponse(
            success=bool(getattr(result, "success", False)),
            output=getattr(result, "output", "") or "",
            error=getattr(result, "error", None),
            images=getattr(result, "images", None) or [],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Kernel execute failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
'''


def main() -> int:
    if not KERNEL_SERVER.exists():
        print(f"{KERNEL_SERVER} does not exist", file=sys.stderr)
        return 1

    text = KERNEL_SERVER.read_text(encoding="utf-8")
    if '@app.post("/kernel/execute"' in text:
        print(f"{KERNEL_SERVER} already has /kernel/execute")
        return 0

    api_marker = "\n# API \u8def\u7531\n"
    if api_marker not in text:
        print("kernel_server.py API marker was not found", file=sys.stderr)
        return 1
    text = text.replace(api_marker, textwrap.dedent(EXECUTE_MODELS) + api_marker, 1)

    route_marker = '\n@app.get("/kernel/connection", response_model=ConnectionInfoResponse)\n'
    if route_marker not in text:
        print("kernel connection route marker was not found", file=sys.stderr)
        return 1
    text = text.replace(route_marker, textwrap.dedent(EXECUTE_ROUTE) + route_marker, 1)

    KERNEL_SERVER.write_text(text, encoding="utf-8")
    print(f"patched {KERNEL_SERVER}: added /kernel/execute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
