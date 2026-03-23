---
Last Updated: 2026-01-09
---

## Deployment Options

OpenContracts is designed to be deployed using Docker Compose. You can run it locally or in a production environment. Follow the instructions below for a local environment if you just want to test it or you want to use it for yourself and don't intend to make the application available to other users via the Internet.

### Local Deployment

#### Quick Start with Default Settings
A "local" deployment is deployed on your personal computer and is not meant to be accessed over the Internet. If you
don't need to configure anything, just follow the quick start guide above to get up and running with a local deployment
without needing any further configuration.

#### Setup .env Files

##### Backend

After cloning this repo to a machine of your choice, create a folder for your environment
files in the repo root. You'll need `./.envs/.local/.django` and `./.envs/.local/.postgres`.

Use the samples in [`docs/sample_env_files/backend/local/`](../sample_env_files/backend/local/) as guidance:
- [`.django`](../sample_env_files/backend/local/.django) - Django configuration
- [`.postgres`](../sample_env_files/backend/local/.postgres) - PostgreSQL configuration

NOTE: You'll need to replace the placeholder passwords and users where noted, but otherwise minimal config should be required.

##### Frontend

You need to create a frontend .env file at `./.envs/.local/.frontend` which holds your configurations for your login
method as well as certain feature switches (e.g. turn off imports).

Use the samples in [`docs/sample_env_files/frontend/local/`](../sample_env_files/frontend/local/):
- [`django.auth.env`](../sample_env_files/frontend/local/django.auth.env) - for Django's built-in auth backend
- [`with.auth0.env`](../sample_env_files/frontend/local/with.auth0.env) - for Auth0 authentication

Local vs production deployments are essentially the same, but the root
url of the backend will change from localhost to wherever you're hosting the application in production.

#### Build the Stack

Once your .env files are setup, build the stack using Docker Compose:

```bash
docker compose -f local.yml build
```

Then bring up the stack:

```bash
docker compose -f local.yml --profile fullstack up
```

**Note:** The first time you run the application, Django will automatically:
- Run database migrations to set up the database schema
- Create a superuser account using the credentials from your `.django` env file (DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, and DJANGO_SUPERUSER_PASSWORD)

The superuser account can log in to both:
- The main application frontend at `http://localhost:3000`
- The admin dashboard at `http://localhost:8000/admin`

If you need to create additional superuser accounts, you can run:

```bash
docker compose -f local.yml run django python manage.py createsuperuser
```

### Production Environment

The production environment is designed to be public-facing and exposed to the Internet, so there are quite a number more configurations required than a local deployment, particularly if you use an AWS S3 storage backend or the Auth0 authentication system.

#### Production Prerequisites

- **Domain name** with DNS configured
- **SSL certificates** (Let's Encrypt recommended via Traefik)
- **Minimum 2 CPU cores and 4GB RAM** (8GB+ recommended)
- **Firewall configured** to allow ports 80 and 443
- **Backup strategy** for database and uploaded files

#### Configuration Steps

After cloning this repo to your production server, you'll need to:

1. **Create production env files** in `.envs/.production/` using the samples from:
   - Backend: [`docs/sample_env_files/backend/production/`](../sample_env_files/backend/production/)
     - [`.django`](../sample_env_files/backend/production/.django) - Django configuration
     - [`.postgres`](../sample_env_files/backend/production/.postgres) - PostgreSQL configuration
     - [`.frontend`](../sample_env_files/backend/production/.frontend) - Frontend configuration
   - Frontend: [`docs/sample_env_files/frontend/production/`](../sample_env_files/frontend/production/)
     - [`django.auth.env`](../sample_env_files/frontend/production/django.auth.env) - for Django's built-in auth backend
     - [`with.auth0.env`](../sample_env_files/frontend/production/with.auth0.env) - for Auth0 authentication
2. **Configure your domain** - This needs to be done in a few places:

First, in `opencontractserver/contrib/sites/migrations`, you'll find a file called `0003_set_site_domain_and_name.py`. BEFORE  running any of your migrations, you should modify the `domain` and `name` defaults you'll fine in `update_site_forward`:

```
def update_site_forward(apps, schema_editor):
 """Set site domain and name.""" Site = apps.get_model("sites", "Site") Site.objects.update_or_create( id=settings.SITE_ID, defaults={ "domain": "contracts.opensource.legal", "name": "OpenContractServer", }, )
```

and `update_site_backward`:

```
def update_site_backward(apps, schema_editor):
 """Revert site domain and name to default.""" Site = apps.get_model("sites", "Site") Site.objects.update_or_create( id=settings.SITE_ID, defaults={"domain": "example.com", "name": "example.com"} )
```

Finally, don't forget to configure Traefik, the router in the docker-compose stack that exposes different containers to
end-users depending on the route (url) received. You need to update the Traefik file at `compose/production/traefik/traefik.yml` in your repository.

If you're using Auth0, see the [Auth0 configuration section](authentication.md#option-2-auth0-authentication).

If you're using AWS S3 for file storage, see the [AWS configuration](choose-storage-backend.md#aws-storage-backend) section. NOTE, the underlying django library that provides cloud storage, django-storages, can also work with other cloud providers such as Azure and GCP. See the django storages library docs for more info.

```bash
docker compose -f production.yml build
```

Then, run migrations (to setup the database). **CRITICAL**: Always run migrations first using the migrate profile:

```bash
docker compose -f production.yml --profile migrate up migrate
```

Then, create a superuser account that can log in to the admin dashboard (in a production deployment this is available at the url set in your env file as the `DJANGO_ADMIN_URL`) by typing this command and following the prompts:

```bash
docker compose -f production.yml run django python manage.py createsuperuser
```

Finally, bring up the stack:

```bash
docker compose -f production.yml up
```

You should now be able to access the OpenContracts frontend by visiting your configured domain (served through Traefik on port 80/443).

## ENV File Configurations

OpenContracts is configured via .env files. For a local deployment, these should go in `.envs/.local`. For production,
use `.envs/.production`. Sample .env files for each deployment environment are provided in:

- Backend samples: [`docs/sample_env_files/backend/`](../sample_env_files/backend/)
  - [`local/`](../sample_env_files/backend/local/) - Local development configuration
  - [`production/`](../sample_env_files/backend/production/) - Production configuration
- Frontend samples: [`docs/sample_env_files/frontend/`](../sample_env_files/frontend/)
  - [`local/`](../sample_env_files/frontend/local/) - Local development configuration
  - [`production/`](../sample_env_files/frontend/production/) - Production configuration

The local configuration should let you deploy the application on your PC without requiring any specific configuration.
The production configuration is meant to provide a web application and requires quite a bit more configuration and
knowledge of web apps.
