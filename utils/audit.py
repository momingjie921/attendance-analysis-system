import json
import logging
from flask import request, session


def audit_log(action, target="", result="success", detail=None):
    payload = {
        "action": action,
        "target": target,
        "result": result,
        "user": session.get("username", "anonymous"),
        "role": session.get("role", "unknown"),
        "ip": request.remote_addr,
        "path": request.path,
    }
    if detail is not None:
        payload["detail"] = detail
    logging.info("AUDIT %s", json.dumps(payload, ensure_ascii=False))
