"""Import every domain of the repository's `domains/` that is not in the database yet (local start-up seed)."""

import os

from sqlalchemy import select

from . import portable, service
from .db import session_scope
from .main import seed as seed_user
from .models import Domain


def main() -> None:
    root = service.domains_root()
    with session_scope() as s:
        user = seed_user(s)
        have = set(s.scalars(select(Domain.slug)))
        for name in sorted(os.listdir(root)):
            if os.path.isdir(os.path.join(root, name)) and name not in have:
                summary = portable.import_domain(s, root, name, user_id=user.id)
                s.commit()
                print(f"imported {name}: " + ", ".join(b["slug"] for b in summary["bots"]))
        if not set(os.listdir(root)) - have:
            print("nothing to import")


if __name__ == "__main__":
    main()
