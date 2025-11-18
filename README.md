# CastMail2List

## Usage

For production use (using gunicorn as WSGI):

```sh
castmail2list --help
```

For local development and administrative commands (using Flask directly):

```sh
castmail2list-cli --help
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
