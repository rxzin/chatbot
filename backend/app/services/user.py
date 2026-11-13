from typing import Type, TypeVar

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.security import hash_password
from core.errors import ConflictError, UnknownError, BadRequest
from schemas.models import User, Roles, user_roles_table
from schemas.schema import UserCreate, UserResponse

ModelType = TypeVar("ModelType")


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles).selectinload(Roles.permissions))
        .where(User.email == email)
    )
    return result.scalar_one_or_none()


async def get_role(db: AsyncSession, model: Type[ModelType], name) -> ModelType | None:
    result = await db.execute(select(model).where(model.name == name))
    return result.scalar_one_or_none()


async def create_user_service(db: AsyncSession, user: UserCreate) -> UserResponse:
    if await get_user_by_email(db, user.email):
        raise ConflictError("Email already exists")

    try:
        db_user = User(email=str(user.email), password=await hash_password(user.password))
        # Add to database
        db.add(db_user)
        await db.flush()
        role_name = "users"
        db_role = await get_role(db, Roles, role_name)

        if not db_role:
            raise BadRequest(
                "Role does not exist in database. Please seed the roles table."
            )

        # db_user.roles.append(db_role)
        await db.execute(
            insert(user_roles_table).values(
                user_id=db_user.id,
                role_id=db_role.id,
            )
        )
        await db.commit()

        return UserResponse(id=db_user.id, email=db_user.email)

    except BadRequest:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise UnknownError(f"Failed to create user: {e}") from e
