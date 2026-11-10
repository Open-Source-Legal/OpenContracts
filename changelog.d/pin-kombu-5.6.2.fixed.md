- **Pinned Kombu to 5.6.2 so Celery workers keep starting.** Celery 5.6.3 only
  declares `kombu>=5.6.0`, and `requirements/base.txt` did not pin Kombu, so
  each image build installed the newest release. Kombu 5.7.0's Redis transport
  binds expiring queues through Lua scripts that call `TIME`. A Redis user that
  isn't allowed that command rejects the script, and the worker exits during
  startup while the web process keeps running. `requirements/base.txt` now pins
  `kombu==5.6.2`, and `.github/dependabot.yml` holds Dependabot below 5.7 until
  a worker has been started against Redis with its deployment permissions.
