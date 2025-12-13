.PHONY: logs status start stop restart install

# Show live logs from the service
logs:
	sudo journalctl -u pi2-rec.service -f

# Show service status
status:
	sudo systemctl status pi2-rec.service

# Start the service
start:
	sudo systemctl start pi2-rec.service

# Stop the service
stop:
	sudo systemctl stop pi2-rec.service

# Restart the service
restart:
	sudo systemctl restart pi2-rec.service

# Install the service
install:
	sudo cp pi2-rec.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable pi2-rec.service
	@echo "Service installed and enabled. Use 'make start' to start it."