# app/repositories/base.py
from __future__ import annotations

from typing import Any, Generic, Iterable, Sequence, TypeVar, overload
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar("T", bound=DeclarativeBase)  # любая декларативная модель


class BaseRepository(Generic[T]):
    """
    Универсальный асинхронный репозиторий для моделей SQLAlchemy 2.x.
    Пример:
        repo = BaseRepository[Order](session, Order)
        await repo.create({...})
        await repo.get_by_id(1)
        await repo.list(limit=20, order_by=["-id"])
        await repo.update(1, {"amount": 2000})
        await repo.delete(1)
    """

    def __init__(self, session: AsyncSession, model: type[T], *, pk_attr: str = "id") -> None:
        self.session = session
        self.model = model
        self.pk_attr = pk_attr  # имя PK поля в модели (по умолчанию "id")

    # ------------------- helpers -------------------

    def _apply_filters(self, stmt: Select, **filters: Any) -> Select:
        """
        Простые фильтры как kwargs: field=value, field__in=[...], field__gt=..., field__lt=...
        Поддержка суффиксов: __in, __gt, __gte, __lt, __lte, __ne, __like, __ilike, __is, __not
        """
        from sqlalchemy import and_, or_

        clauses = []
        for raw_key, value in filters.items():
            if value is None:
                continue

            # поддержка OR через ключи вида: __or=[{"status":"X"}, {"status":"Y"}]
            if raw_key == "__or" and isinstance(value, Iterable):
                or_clauses = []
                for item in value:
                    if isinstance(item, dict):
                        or_clauses.append(and_(*self._dict_to_clauses(item)))
                if or_clauses:
                    clauses.append(or_(*or_clauses))
                continue

            # обычные поля
            clauses += self._dict_to_clauses({raw_key: value})

        if clauses:
            from sqlalchemy import and_
            stmt = stmt.where(and_(*clauses))
        return stmt

    def _dict_to_clauses(self, dct: dict[str, Any]):
        from sqlalchemy import or_
        clauses = []
        for key, value in dct.items():
            field, *op = key.split("__", 1)
            column = getattr(self.model, field)

            operator = op[0] if op else "eq"
            if operator == "eq":
                clauses.append(column == value)
            elif operator == "ne":
                clauses.append(column != value)
            elif operator == "gt":
                clauses.append(column > value)
            elif operator == "gte":
                clauses.append(column >= value)
            elif operator == "lt":
                clauses.append(column < value)
            elif operator == "lte":
                clauses.append(column <= value)
            elif operator == "in":
                clauses.append(column.in_(value))
            elif operator == "like":
                clauses.append(column.like(value))
            elif operator == "ilike":
                clauses.append(column.ilike(value))
            elif operator == "is":
                clauses.append(column.is_(value))
            elif operator == "not":
                clauses.append(~column.in_(value) if isinstance(value, (list, tuple, set)) else ~ (column == value))
            else:
                raise ValueError(f"Unsupported filter operator: {operator}")
        return clauses

    def _apply_order(self, stmt: Select, order_by: Sequence[str] | None) -> Select:
        """
        order_by: ["id", "-created_at", "amount"]  (минус = DESC)
        """
        if not order_by:
            return stmt
        orders = []
        for key in order_by:
            desc = key.startswith("-")
            name = key[1:] if desc else key
            col = getattr(self.model, name)
            orders.append(col.desc() if desc else col.asc())
        return stmt.order_by(*orders)

    # ------------------- CRUD -------------------

    async def create(self, data: dict[str, Any]) -> T:
        obj = self.model(**data)  # type: ignore[arg-type]
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def create_many(self, rows: Iterable[dict[str, Any]]) -> list[T]:
        objs = [self.model(**r) for r in rows]  # type: ignore[misc]
        self.session.add_all(objs)
        await self.session.commit()
        # refresh для пачки обычно не нужен, если нет server_defaults
        return objs

    async def get_by_id(self, pk: Any) -> T | None:
        return await self.session.get(self.model, pk)

    async def get_one(self, **filters: Any) -> T | None:
        stmt = self._apply_filters(select(self.model), **filters).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Sequence[str] | None = None,
        **filters: Any,
    ) -> list[T]:
        stmt = select(self.model)
        stmt = self._apply_filters(stmt, **filters)
        stmt = self._apply_order(stmt, order_by)
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return res.scalars().all() # type:ignore

    async def count(self, **filters: Any) -> int:
        from sqlalchemy import select
        stmt = self._apply_filters(select(func.count("*")), **filters).select_from(self.model)
        res = await self.session.execute(stmt)
        return int(res.scalar() or 0)

    async def exists(self, **filters: Any) -> bool:
        return (await self.count(**filters)) > 0

    async def update(self, pk: Any, data: dict[str, Any]) -> T | None:
        obj = await self.get_by_id(pk)
        if not obj:
            return None
        for k, v in data.items():
            setattr(obj, k, v)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def update_one(self, data: dict[str, Any], **filters: Any) -> T | None:
        """
        Обновляет одну запись, найденную по фильтрам.
        Возвращает обновлённый объект или None, если не найдено.
        """
        obj = await self.get_one(**filters)
        if not obj:
            return None

        for k, v in data.items():
            setattr(obj, k, v)

        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def update_where(self, data: dict[str, Any], **filters: Any) -> int:
        """
        Массовое обновление. Возвращает кол-во обновлённых строк.
        """
        stmt = update(self.model).values(**data).execution_options(synchronize_session="fetch")
        stmt = self._apply_filters(stmt, **filters) # type:ignore
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount or 0 # type:ignore

    async def delete(self, pk: Any) -> bool:
        pk_col = getattr(self.model, self.pk_attr)
        stmt = delete(self.model).where(pk_col == pk).returning(pk_col)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.scalar_one_or_none() is not None

    async def delete_where(self, **filters: Any) -> int:
        """
        Массовое удаление по фильтрам. Возвращает кол-во удалённых строк.
        """
        stmt = delete(self.model)
        stmt = self._apply_filters(stmt, **filters) # type:ignore
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount or 0 # type:ignore
