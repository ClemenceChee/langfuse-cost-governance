"""Load synthetic demo data into the configured warehouse.

Run:  docker compose run --rm api python seed_demo.py
"""
import os

from warehouse import demo, get_warehouse

DSN = os.getenv(
    "DATABASE_URL", "postgresql://analytics:analytics@localhost:5433/analytics"
)


def main() -> None:
    n = demo.seed(get_warehouse(DSN))
    print(f"Seeded {n} demo observations across 30 days.")


if __name__ == "__main__":
    main()
