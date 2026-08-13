// PM2 process manager config, as an alternative to the systemd unit
// (deploy/natsukashi.service). Use one or the other, not both.
//
// Setup on the server:
//   sudo apt install -y nodejs npm
//   sudo npm install -g pm2
//   cd ~/Natsukashi_Main
//   pm2 start deploy/ecosystem.config.js
//   pm2 save
//   pm2 startup   # follow the printed command to enable PM2 on reboot
//
// Common commands:
//   pm2 status
//   pm2 logs natsukashi
//   pm2 restart natsukashi
//   pm2 stop natsukashi

module.exports = {
  apps: [
    {
      name: 'natsukashi',
      cwd: '/home/ubuntu/Natsukashi_Main',
      script: '.venv/bin/gunicorn',
      args: 'natsukashi_design.wsgi:application --workers 3 --bind unix:/home/ubuntu/Natsukashi_Main/natsukashi.sock',
      interpreter: 'none',
      env: {
        // gunicorn reads settings via Django, which loads .env itself
        // (python-dotenv) - no extra env vars needed here.
      },
      autorestart: true,
      max_restarts: 10,
    },
  ],
};
