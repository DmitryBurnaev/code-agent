# Database Architecture

This module provides a modern database architecture with multiple approaches for different use cases.

## Architecture Overview

### 1. ContextVar-based Session Management
- Uses `ContextVar` for async context management instead of global variables
- Session factory and engine are initialized once per application lifecycle
- Proper resource cleanup on application shutdown

### 2. Multiple Access Patterns

#### Simple CRUD Operations (Dependency Injection)
```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.dependencies import get_db_session
from src.db.repositories import UserRepository

async def get_user(id: int, session: AsyncSession = Depends(get_db_session)):
    user_repo = UserRepository(session=session)
    return await user_repo.get(id)
```

#### Complex Atomic Operations (UOW with DI)
```python
from fastapi import Depends
from src.db.services import SASessionUOW
from src.db.dependencies import get_uow_with_session
from src.db.repositories import UserRepository, TokenRepository, VendorRepository

async def create_user_with_tokens(user_data: dict, token_data: dict, uow: SASessionUOW = Depends(get_uow_with_session)):
    async with uow:
        # Multiple operations in one transaction using repositories
        user_repo = UserRepository(session=uow.session)
        token_repo = TokenRepository(session=uow.session)
        vendor_repo = VendorRepository(session=uow.session)
        
        # Create user
        user = await user_repo.create(user_data)
        
        # Create token for user
        token_data["user_id"] = user.id
        token = await token_repo.create(token_data)
        
        # Update vendor statistics
        vendors = await vendor_repo.all()
        # ... business logic ...
        
        # Explicit commit control
        uow.mark_for_commit()
        
        return {"user": user, "token": token}
```

#### Legacy UOW Pattern (Standalone)
```python
from src.db.services import SASessionUOW
from src.db.repositories import UserRepository, TokenRepository

async def legacy_operation():
    async with SASessionUOW() as uow:
        # Multiple operations in one transaction using repositories
        user_repo = UserRepository(session=uow.session)
        token_repo = TokenRepository(session=uow.session)
        
        user = await user_repo.create({"name": "John", "email": "john@example.com"})
        token = await token_repo.create({"user_id": user.id, "type": "api"})
        
        uow.need_to_commit = True
```

## Dependencies

### `get_db_session()`
- **Use case**: Simple CRUD operations
- **Behavior**: Automatic commit/rollback on request completion
- **Best for**: Single operations, read operations, simple writes

### `get_transactional_session()`
- **Use case**: Complex operations requiring explicit transaction control
- **Behavior**: Starts transaction, but requires manual commit/rollback
- **Best for**: When you need fine-grained control over transactions

### `get_uow_with_session()`
- **Use case**: Complex atomic operations with UOW pattern
- **Behavior**: Combines DI session lifecycle with UOW transaction control
- **Best for**: Complex business logic requiring multiple operations

## UOW Modes

### Standalone Mode
```python
async with SASessionUOW() as uow:
    # UOW creates and manages its own session
    # Full control over session lifecycle
    user_repo = UserRepository(session=uow.session)
    user = await user_repo.get(1)
```

### Dependency Mode
```python
async def endpoint(uow: SASessionUOW = Depends(get_uow_with_session)):
    async with uow:
        # UOW uses session from dependency injection
        # Session lifecycle managed by DI, transaction by UOW
        vendor_repo = VendorRepository(session=uow.session)
        vendors = await vendor_repo.all()
```

## Transaction Control

### Explicit Commit
```python
async with uow:
    user_repo = UserRepository(session=uow.session)
    token_repo = TokenRepository(session=uow.session)
    
    user = await user_repo.create(user_data)
    token = await token_repo.create(token_data)
    
    uow.mark_for_commit()
```

### Explicit Rollback
```python
async with uow:
    try:
        user_repo = UserRepository(session=uow.session)
        user = await user_repo.create(user_data)
        
        # Validate business rules
        if not user.is_valid():
            raise ValueError("Invalid user data")
            
        uow.mark_for_commit()
    except Exception:
        await uow.rollback()
        raise
```

### Automatic Rollback on Exception
```python
async with uow:
    user_repo = UserRepository(session=uow.session)
    token_repo = TokenRepository(session=uow.session)
    
    user = await user_repo.create(user_data)
    token = await token_repo.create(token_data)
    
    # If any operation fails, entire transaction is rolled back
    uow.mark_for_commit()
```

## Migration Guide

### From Old UOW to New UOW
```python
# Old way
async with SASessionUOW() as uow:
    user_repo = UserRepository(session=uow.session)
    user = await user_repo.create(user_data)
    uow.need_to_commit = True

# New way (same interface, improved internals)
async with SASessionUOW() as uow:
    user_repo = UserRepository(session=uow.session)
    user = await user_repo.create(user_data)
    uow.mark_for_commit()  # or keep uow.need_to_commit = True
```

### From Manual Sessions to DI
```python
# Old way
async def endpoint():
    async with session_scope() as session:
        user_repo = UserRepository(session=session)
        user = await user_repo.get(1)

# New way
async def endpoint(session: AsyncSession = Depends(get_db_session)):
    user_repo = UserRepository(session=session)
    user = await user_repo.get(1)
```

### From Manual Sessions to UOW with DI
```python
# Old way
async def complex_endpoint():
    async with session_scope() as session:
        user_repo = UserRepository(session=session)
        token_repo = TokenRepository(session=session)
        
        user = await user_repo.create(user_data)
        token = await token_repo.create(token_data)
        await session.commit()

# New way
async def complex_endpoint(uow: SASessionUOW = Depends(get_uow_with_session)):
    async with uow:
        user_repo = UserRepository(session=uow.session)
        token_repo = TokenRepository(session=uow.session)
        
        user = await user_repo.create(user_data)
        token = await token_repo.create(token_data)
        uow.mark_for_commit()
```

## Real-world Examples

### Simple User Retrieval
```python
@router.get("/users/{user_id}")
async def get_user(user_id: int, session: AsyncSession = Depends(get_db_session)):
    user_repo = UserRepository(session=session)
    return await user_repo.get(user_id)
```

### Complex User Registration
```python
@router.post("/users/register")
async def register_user(user_data: dict, uow: SASessionUOW = Depends(get_uow_with_session)):
    async with uow:
        user_repo = UserRepository(session=uow.session)
        token_repo = TokenRepository(session=uow.session)
        
        # Check if user already exists
        existing_user = await user_repo.first(email=user_data["email"])
        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")
        
        # Create user
        user = await user_repo.create(user_data)
        
        # Create default token
        token = await token_repo.create({
            "user_id": user.id,
            "type": "default",
            "is_active": True
        })
        
        uow.mark_for_commit()
        
        return {"user": user, "token": token}
```

### Vendor Management with Statistics
```python
@router.post("/vendors/{vendor_id}/activate")
async def activate_vendor(vendor_id: int, uow: SASessionUOW = Depends(get_uow_with_session)):
    async with uow:
        vendor_repo = VendorRepository(session=uow.session)
        token_repo = TokenRepository(session=uow.session)
        
        # Get vendor
        vendor = await vendor_repo.get(vendor_id)
        
        # Update vendor status
        await vendor_repo.update(vendor, is_active=True)
        
        # Create activation token
        token = await token_repo.create({
            "vendor_id": vendor.id,
            "type": "activation",
            "expires_at": datetime.now() + timedelta(days=7)
        })
        
        # Update statistics
        active_vendors = await vendor_repo.all(is_active=True)
        vendor.active_count = len(active_vendors)
        await vendor_repo.update(vendor, active_count=vendor.active_count)
        
        uow.mark_for_commit()
        
        return {"vendor": vendor, "activation_token": token}
```

## Best Practices

1. **Use DI for simple operations**: `get_db_session()` for single CRUD operations
2. **Use UOW for complex operations**: `get_uow_with_session()` for multi-step business logic
3. **Always use repositories**: Don't work directly with sessions, use repository pattern
4. **Explicit commit control**: Always use `uow.mark_for_commit()` for write operations
5. **Exception handling**: Let UOW handle rollback automatically on exceptions
6. **Session ownership**: Be aware of whether UOW owns the session or uses DI session

## Performance Benefits

- **Connection pooling**: Single engine instance with proper pool configuration
- **Session reuse**: Sessions are created from factory, not new engines
- **Context isolation**: ContextVar ensures proper async context management
- **Resource cleanup**: Proper disposal of resources on application shutdown
