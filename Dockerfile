# Use Python 3.9 as the base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies including those needed for Playwright
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install

# Copy project files
COPY . .

# Create a wrapper script to initialize the asyncio event loop
RUN echo '#!/usr/bin/env python3\nimport asyncio\nimport nest_asyncio\nimport os\nimport sys\n\n# Apply nest_asyncio to allow nested event loops\nnest_asyncio.apply()\n\n# Set the asyncio event loop policy for streamlit\nasyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())\n\n# Create a new event loop\nloop = asyncio.new_event_loop()\nasyncio.set_event_loop(loop)\n\n# Run streamlit\nos.system("streamlit " + " ".join(sys.argv[1:]))' > /app/start.py && \
    chmod +x /app/start.py

# Install nest_asyncio
RUN pip install nest_asyncio

# Expose the Streamlit port
EXPOSE 8501

# Command to run the application using the wrapper script
CMD ["python", "/app/start.py", "run", "streamlit_app.py"]