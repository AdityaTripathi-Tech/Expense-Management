FROM odoo:17.0

# Install system dependencies for OCR and image processing
USER root
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    libleptonica-dev \
    pkg-config \
    python3-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy the custom module
COPY smart_expense_management /mnt/extra-addons/smart_expense_management/

# Copy configuration files
COPY odoo.conf /etc/odoo/
COPY entrypoint.sh /

# Set proper permissions
RUN chown -R odoo:odoo /mnt/extra-addons/smart_expense_management
RUN chmod +x /entrypoint.sh

# Switch back to odoo user
USER odoo

# Set environment variables
ENV ODOO_RC=/etc/odoo/odoo.conf
ENV ADDONS_PATH=/mnt/extra-addons

# Expose port
EXPOSE 8069

# Use custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
