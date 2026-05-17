# Mobile User Experience

To use OpenLumara on a phone, the best options are the WebUI (which grants full privacy if self-hosted), the Telegram channel, and the Matrix channel.

The WebUI can be installed on a phone as a pseudo-app because it is a PWA (Progressive Web App). To make that work, the WebUI needs to be hosted on a valid HTTPS server with a valid certificate. A great way to do that is to use `caddy` and `mkcert` if you're running locally. Once set up, open the webui url in your chosen browser and find that browser's `install this page` button (depends on your browser), then use that!
