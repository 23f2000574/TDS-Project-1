# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /code

# Copy the requirements file into the container at /code
COPY ./requirements.txt /code/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the rest of the application's code into the container
# This will copy your entire 'app' folder
COPY ./app /code/app

# Make port 7860 available to the world outside this container
EXPOSE 7860

# Run uvicorn server when the container launches
# This now correctly points to main.py inside the app folder
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]

