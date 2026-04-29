import asyncio

from app.services.job_watchdog import recover_stale_jobs


async def main() -> None:
    count = await recover_stale_jobs()
    print(f"Recovered {count} stale jobs")


if __name__ == "__main__":
    asyncio.run(main())
