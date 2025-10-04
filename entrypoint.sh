#!/bin/bash
set -e

# Function to wait for postgres
wait_for_postgres() {
    echo "Waiting for PostgreSQL to be ready..."
    while ! pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER"; do
        sleep 1
    done
    echo "PostgreSQL is ready!"
}

# Wait for database if in Docker environment
if [ -n "$POSTGRES_HOST" ]; then
    wait_for_postgres
fi

# Initialize database if it doesn't exist
if [ "$1" = 'odoo' ]; then
    # Check if database exists
    DB_EXISTS=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -lqt | cut -d \| -f 1 | grep -w "$POSTGRES_DB" | wc -l)
    
    if [ "$DB_EXISTS" = "0" ]; then
        echo "Database $POSTGRES_DB does not exist. Creating and initializing..."
        
        # Create database
        createdb -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB"
        
        # Initialize Odoo with the smart_expense_management module
        odoo \
            --addons-path="/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons" \
            --database="$POSTGRES_DB" \
            --db_host="$POSTGRES_HOST" \
            --db_port="$POSTGRES_PORT" \
            --db_user="$POSTGRES_USER" \
            --db_password="$POSTGRES_PASSWORD" \
            --init="smart_expense_management" \
            --stop-after-init \
            --without-demo=False
        
        echo "Database initialized successfully!"
    else
        echo "Database $POSTGRES_DB already exists."
    fi
    
    # Start Odoo normally
    exec odoo \
        --addons-path="/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons" \
        --database="$POSTGRES_DB" \
        --db_host="$POSTGRES_HOST" \
        --db_port="$POSTGRES_PORT" \
        --db_user="$POSTGRES_USER" \
        --db_password="$POSTGRES_PASSWORD" \
        --xmlrpc-port=8069 \
        --longpolling-port=8072 \
        --workers=0 \
        --max-cron-threads=1 \
        --log-level=info
else
    exec "$@"
fi
