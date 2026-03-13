import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from sqlalchemy import MetaData, Table, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import verify_api_key
from database import engine, get_db

router = APIRouter(tags=["tables"])

_cache: dict[str, Table] = {}
_SAFE_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


async def _get_table(name: str) -> Table:
    if not _SAFE_NAME.match(name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid table name.")

    if name in _cache:
        return _cache[name]

    meta = MetaData()
    async with engine.connect() as conn:
        await conn.run_sync(meta.reflect, only=[name])

    if name not in meta.tables:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    _cache[name] = meta.tables[name]
    return _cache[name]


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row._mapping)


@router.get("/{table}")
async def list_rows(
    table: str = Path(...),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> list[dict[str, Any]]:
    tbl = await _get_table(table)
    result = await db.execute(select(tbl).limit(limit).offset(offset))
    return [_row_to_dict(row) for row in result.fetchall()]


@router.post("/{table}", status_code=status.HTTP_201_CREATED)
async def create_row(
    table: str = Path(...),
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict[str, Any]:
    tbl = await _get_table(table)
    valid = {c.name for c in tbl.columns}
    data = {k: v for k, v in payload.items() if k in valid}

    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid columns in request body.",
        )

    result = await db.execute(insert(tbl).values(**data).returning(*tbl.columns))
    await db.commit()
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Insert failed.")
    return _row_to_dict(row)


@router.put("/{table}/{id}")
async def update_row(
    table: str = Path(...),
    id: int = Path(...),
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> dict[str, Any]:
    tbl = await _get_table(table)

    if "id" not in tbl.c:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table does not support this operation.",
        )

    valid = {c.name for c in tbl.columns if c.name != "id"}
    data = {k: v for k, v in payload.items() if k in valid}

    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid columns in request body.",
        )

    result = await db.execute(
        update(tbl).where(tbl.c.id == id).values(**data).returning(*tbl.columns)
    )
    await db.commit()
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return _row_to_dict(row)


@router.delete("/{table}/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_row(
    table: str = Path(...),
    id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
) -> None:
    tbl = await _get_table(table)

    if "id" not in tbl.c:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table does not support this operation.",
        )

    result = await db.execute(
        delete(tbl).where(tbl.c.id == id).returning(tbl.c.id)
    )
    await db.commit()
    if not result.fetchone():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
