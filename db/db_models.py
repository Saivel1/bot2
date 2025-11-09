from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime
from sqlalchemy import func, ForeignKey


class Base(DeclarativeBase):
    pass


class PaymentData(Base):
    __tablename__ = 'payment_data'
    
    payment_id: Mapped[str] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.user_id'))
    status: Mapped[str] = mapped_column(server_default='pending')
    amount: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    applied: Mapped[bool] = mapped_column(default=False)
    
    # Опционально: relationship для удобства
    user: Mapped["UserOrm"] = relationship(back_populates="payments")


class UserOrm(Base):
    __tablename__ = "users"
    
    user_id: Mapped[str] = mapped_column(primary_key=True)
    username: Mapped[str | None]
    trial_used: Mapped[bool] = mapped_column(default=False)
    subscription_end: Mapped[datetime | None]
    
    # Опционально: relationship
    payments: Mapped[list["PaymentData"]] = relationship(back_populates="user")


class LinksOrm(Base):
    __tablename__ = 'links'

    user_id: Mapped[str] = mapped_column(primary_key=True)
    uuid: Mapped[str]
    panel_1: Mapped[str | None]
    panel_2: Mapped[str | None]