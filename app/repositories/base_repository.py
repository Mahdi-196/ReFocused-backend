from typing import TypeVar, Generic, Type, List, Optional, Union, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.future import select as future_select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.db.database import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """
    Base repository class for database operations.
    
    This class provides common CRUD operations for database models.
    It uses SQLAlchemy's async API for database operations.
    """
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize the repository with a model class and session.
        
        Args:
            model: The SQLAlchemy model class
            session: SQLAlchemy AsyncSession
        """
        self.model = model
        self.session = session
    
    async def get_by_id(self, id: Any, options=None) -> Optional[ModelType]:
        """
        Get a model instance by ID with optional eager loading.
        
        Args:
            id: The primary key value
            options: Optional eager loading options
            
        Returns:
            Model instance or None
        """
        query = select(self.model).where(self.model.id == id)
        if options:
            query = query.options(options)
        result = await self.session.execute(query)
        return result.scalars().first()
    
    async def get_all(self, skip: int = 0, limit: int = 100, options=None) -> List[ModelType]:
        """
        Get all model instances with pagination.
        
        Args:
            skip: Number of items to skip
            limit: Maximum number of items to return
            options: Optional eager loading options
            
        Returns:
            List of model instances
        """
        query = select(self.model).offset(skip).limit(limit)
        if options:
            query = query.options(options)
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def create(self, obj_in: Union[Dict[str, Any], BaseModel]) -> ModelType:
        """
        Create a new model instance.
        
        Args:
            obj_in: Input data as dict or Pydantic model
            
        Returns:
            Created model instance
        """
        if isinstance(obj_in, dict):
            obj_data = obj_in
        else:
            obj_data = obj_in.dict(exclude_unset=True)
        
        db_obj = self.model(**obj_data)
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj
    
    async def update(self, 
                    id: Any, 
                    obj_in: Union[Dict[str, Any], BaseModel],
                    exclude_unset: bool = True) -> Optional[ModelType]:
        """
        Update a model instance.
        
        Args:
            id: The primary key value
            obj_in: Input data as dict or Pydantic model
            exclude_unset: Whether to exclude unset fields from update
            
        Returns:
            Updated model instance or None if not found
        """
        db_obj = await self.get_by_id(id)
        if db_obj is None:
            return None
        
        update_data = obj_in
        if not isinstance(update_data, dict):
            update_data = update_data.dict(exclude_unset=exclude_unset)
        
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj
    
    async def delete(self, id: Any) -> bool:
        """
        Delete a model instance by ID.
        
        Args:
            id: The primary key value
            
        Returns:
            True if deleted, False if not found
        """
        db_obj = await self.get_by_id(id)
        if db_obj is None:
            return False
        
        await self.session.delete(db_obj)
        return True
    
    async def count(self, filters=None) -> int:
        """
        Count model instances, optionally with filters.
        
        Args:
            filters: Optional query filters
            
        Returns:
            Count of model instances
        """
        query = select(func.count(self.model.id))
        if filters:
            query = query.where(filters)
        result = await self.session.execute(query)
        return result.scalar() 