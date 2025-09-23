# API Reference

## Core Classes

### Cancellable

The main class for managing cancellable operations.

```python
class Cancellable:
    def __init__(
        self,
        operation_id: Optional[str] = None,
        name: Optional[str] = None,
        parent: Optional['Cancellable'] = None,
        metadata: Optional[Dict[str, Any]] = None,
        register_globally: bool = False,
    )
```

#### Factory Methods

##### with_timeout
```python
@classmethod
def with_timeout(
    cls,
    timeout: Union[float, timedelta],
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs
) -> 'Cancellable'
```
Create a cancellable that times out after the specified duration.

##### with_token
```python
@classmethod
def with_token(
    cls,
    token: CancellationToken,
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs
) -> 'Cancellable'
```
Create a cancellable controlled by a cancellation token.

##### with_signal
```python
@classmethod
def with_signal(
    cls,
    *signals: int,
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs
) -> 'Cancellable'
```
Create a cancellable that responds to OS signals.

##### with_condition
```python
@classmethod
def with_condition(
    cls,
    condition: Callable[[], Union[bool, Awaitable[bool]]],
    check_interval: float = 0.1,
    condition_name: Optional[str] = None,
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
    **kwargs
) -> 'Cancellable'
```
Create a cancellable that monitors a condition.

#### Methods

##### combine
```python
def combine(self, *others: 'Cancellable') -> 'Cancellable'
```
Combine multiple cancellables into one.

##### stream
```python
async def stream(
    self,
    async_iter: AsyncIterator[T],
    report_interval: Optional[int] = None,
    buffer_partial: bool = True,
) -> AsyncIterator[T]
```
Wrap an async iterator with cancellation support.

##### shield
```python
@asynccontextmanager
async def shield(self) -> AsyncIterator['Cancellable']
```
Create a shielded context that won't be cancelled.

##### cancel
```python
async def cancel(
    self,
    reason: CancellationReason = CancellationReason.MANUAL,
    message: Optional[str] = None,
    propagate_to_children: bool = True,
) -> None
```
Cancel the operation.

#### Callbacks

- `on_progress(callback)`: Register progress callback
- `on_start(callback)`: Register start callback
- `on_complete(callback)`: Register completion callback
- `on_cancel(callback)`: Register cancellation callback
- `on_error(callback)`: Register error callback

### CancellationToken

Thread-safe token for manual cancellation.

```python
class CancellationToken:
    async def cancel(
        self,
        reason: CancellationReason = CancellationReason.MANUAL,
        message: Optional[str] = None,
    ) -> bool

    async def wait_for_cancel(self) -> None

    def check(self) -> None  # Raises if cancelled

    async def check_async(self) -> None  # Async version

    def is_cancellation_requested(self) -> bool
```

### OperationRegistry

Global registry for operation management.

```python
class OperationRegistry:
    @classmethod
    def get_instance(cls) -> 'OperationRegistry'

    async def register(self, operation: Cancellable) -> None

    async def get_operation(self, operation_id: str) -> Optional[Cancellable]

    async def list_operations(
        self,
        status: Optional[OperationStatus] = None,
        parent_id: Optional[str] = None,
        name_pattern: Optional[str] = None,
    ) -> List[OperationContext]

    async def cancel_operation(
        self,
        operation_id: str,
        reason: CancellationReason = CancellationReason.MANUAL,
        message: Optional[str] = None,
    ) -> bool
```

## Enums

### OperationStatus
- `PENDING`: Operation created but not started
- `RUNNING`: Operation is currently executing
- `COMPLETED`: Operation completed successfully
- `CANCELLED`: Operation was cancelled
- `FAILED`: Operation failed with error
- `TIMEOUT`: Operation timed out
- `SHIELDED`: Operation is in shielded section

### CancellationReason
- `TIMEOUT`: Cancelled due to timeout
- `MANUAL`: Cancelled manually via token or API
- `SIGNAL`: Cancelled by OS signal
- `CONDITION`: Cancelled by condition check
- `PARENT`: Cancelled because parent was cancelled
- `ERROR`: Cancelled due to error

## Decorators

### @cancellable
```python
@cancellable(
    timeout: Optional[Union[float, timedelta]] = None,
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
    register_globally: bool = False,
    inject_param: Optional[str] = "cancellable",
)
```
Decorator to make async functions cancellable.

### @cancellable_method
```python
@cancellable_method(
    timeout: Optional[Union[float, timedelta]] = None,
    name: Optional[str] = None,
    register_globally: bool = False,
)
```
Decorator for async methods (automatically includes class name).

## Utility Functions

### with_timeout
```python
async def with_timeout(
    timeout: Union[float, timedelta],
    coro: Awaitable[T],
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
) -> T
```
Run a coroutine with timeout.

### cancellable_stream
```python
async def cancellable_stream(
    stream: AsyncIterator[T],
    timeout: Optional[Union[float, timedelta]] = None,
    token: Optional[CancellationToken] = None,
    report_interval: Optional[int] = None,
    on_progress: Optional[Callable[[int, T], Any]] = None,
    buffer_partial: bool = False,
    operation_id: Optional[str] = None,
    name: Optional[str] = None,
) -> AsyncIterator[T]
```
Make any async iterator cancellable.

## Exceptions

- `CancellationError`: Base exception for cancellation
- `TimeoutCancellation`: Operation timed out
- `ManualCancellation`: Operation cancelled manually
- `SignalCancellation`: Operation cancelled by signal
- `ConditionCancellation`: Operation cancelled by condition
- `ParentCancellation`: Operation cancelled by parent
