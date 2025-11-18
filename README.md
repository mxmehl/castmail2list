# CastMail2List

## Usage

In production with gunicorn:

```sh
gunicorn "castmail2list.wsgi:app" -c gunicorn.conf.py -e CONFIG_FILE=/path/to/config.yaml
```

For local development:

```sh
poetry run castmail2list
```


## Configuration

CastMail2List supports loading configuration from YAML files. There are some defaults and some required configuration keys.

### Using YAML Configuration

1. Copy the example configuration file:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. Edit `config.yaml` with your settings

3. Run the application with the `--config` flag:
   ```bash
   castmail2list --config config.yaml
   ```

### Example Configuration File

See `config.example.yaml` for a complete example with all available configuration options.
