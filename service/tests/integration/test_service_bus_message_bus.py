import pytest

from procurawise.shared.messaging import Message, ServiceBusMessageBus

pytestmark = pytest.mark.docker_servicebus

# Fixed, documented value for the official Service Bus emulator - not a
# secret (same category as Azurite's "UseDevelopmentStorage=true"). Queue
# name matches docker/servicebus-emulator/config.json.
_EMULATOR_CONNECTION_STRING = (
    "Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;"
    "SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
)
_QUEUE = "ai-requirement-generation"


@pytest.fixture
def bus() -> ServiceBusMessageBus:
    return ServiceBusMessageBus(_EMULATOR_CONNECTION_STRING)


@pytest.fixture(autouse=True)
def _drain_queue(bus: ServiceBusMessageBus):
    while bus.consume(_QUEUE) is not None:
        pass
    yield
    while bus.consume(_QUEUE) is not None:
        pass


def test_publish_then_consume_round_trips_payload(bus: ServiceBusMessageBus) -> None:
    bus.publish(_QUEUE, {"job_id": "job-1", "tenant_id": "tenant-a"})

    message = bus.consume(_QUEUE)

    assert message == Message(topic=_QUEUE, payload={"job_id": "job-1", "tenant_id": "tenant-a"})


def test_consume_returns_none_when_queue_empty(bus: ServiceBusMessageBus) -> None:
    assert bus.consume(_QUEUE) is None


def test_consume_completes_message_not_redelivered(bus: ServiceBusMessageBus) -> None:
    bus.publish(_QUEUE, {"job_id": "job-2"})
    first = bus.consume(_QUEUE)
    second = bus.consume(_QUEUE)

    assert first is not None
    assert second is None


def test_publish_preserves_fifo_order_for_sequential_jobs(bus: ServiceBusMessageBus) -> None:
    bus.publish(_QUEUE, {"job_id": "job-a"})
    bus.publish(_QUEUE, {"job_id": "job-b"})

    first = bus.consume(_QUEUE)
    second = bus.consume(_QUEUE)

    assert first is not None and first.payload["job_id"] == "job-a"
    assert second is not None and second.payload["job_id"] == "job-b"
