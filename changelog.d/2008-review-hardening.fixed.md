- `emit_analysis_status_notification` (`opencontractserver/notifications/signals.py`)
  no longer hydrates the full `Analyzer` row via a deferred FK load on every
  qualifying `Analysis.save()`: the existing gate query now also captures
  `task_name` (`values_list(...).first()`) and the notification `data` dict
  reuses it instead of `instance.analyzer.task_name`. Also corrected the
  handler docstring, which wrongly claimed WebSocket delivery was automatic via
  a `post_save` receiver on `Notification` (there is none — the explicit
  `broadcast_notification_via_websocket(...)` call is required).
