"""Drain loop that moves queued messages through the sender.

``drain`` takes batches from a ``FifoQueue`` until the queue is empty or the batch
limit is reached. Each message is handed to the sender. A message whose delivery
fails for good is recorded in the returned report and does not stop the drain.
"""


def drain(queue, sender, batch_size, max_batches=None):
    """Deliver queued messages and return a report dict.

    The report has the keys ``delivered``, ``failed`` and ``batches``. ``failed`` is
    a list of ``(message, error_name)`` pairs.
    """
    report = {"delivered": 0, "failed": [], "batches": 0}
    while len(queue) > 0:
        if max_batches is not None and report["batches"] >= max_batches:
            break
        batch = queue.pop_batch(batch_size)
        report["batches"] += 1
        for message in batch:
            try:
                sender.send(message)
            except Exception as err:  # noqa: BLE001
                report["failed"].append((message, type(err).__name__))
                continue
            report["delivered"] += 1
    return report
