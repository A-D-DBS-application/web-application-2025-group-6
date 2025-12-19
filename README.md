[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/DxqGQVx4)

Figma UI link: 
https://comet-cow-17802690.figma.site

Link to OneDrive of video recordings with external partner: 
https://ugentbe-my.sharepoint.com/:f:/r/personal/laurien_duplacie_ugent_be/Documents/video%20recordings%20externe%20partner?csf=1&web=1&e=dMuq1O

MVP Handover Assignment Agreement:
[MVP%20Handover%20%26%20IP%20Assignment%20Agreement%20%282%29.pdf](https://github.com/user-attachments/files/24221161/MVP.20Handover.20.26.20IP.20Assignment.20Agreement.20.282.29.pdf)

# AfriGuide - Travel Planning MVP

A Flask-based web application for planning personalized travel itineraries to African destinations.

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- PostgreSQL database (or use the provided Supabase connection)

## Installation

1. **Clone the repository** (if applicable):
   ```bash
   git clone <repository-url>
   cd travel_mvp
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure the database** (if needed):
   - The application is pre-configured to use a Supabase PostgreSQL database
   - If you need to change the database connection, edit `config.py` and update the `SQLALCHEMY_DATABASE_URI`

6. **Set up environment variables** (optional):
   - Create a `.env` file in the root directory if you want to use environment variables
   - Set `SECRET_KEY` for Flask session security (defaults to "change_me" if not set)

7. **Run database migrations** (if needed):
   ```bash
   flask db upgrade
   ```

## Running the Application

1. **Make sure your virtual environment is activated**

2. **Run the Flask development server**:
   ```bash
   python run.py
   ```
   
   Or alternatively:
   ```bash
   flask run
   ```

3. **Access the application**:
   - Open your web browser and navigate to: `http://127.0.0.1:5000` or `http://localhost:5000`

## Production Deployment

For production deployment, use Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 "run:app"
```

## Project Structure

- `app/` - Main application package
  - `routes/` - Route handlers (main, auth, API, itinerary)
  - `templates/` - Jinja2 HTML templates
  - `static/` - Static files (CSS, images)
  - `models.py` - Database models
  - `optimizer.py` - TSP route optimization
- `config.py` - Application configuration
- `requirements.txt` - Python dependencies
- `run.py` - Application entry point

## Features

- Destination selection (Uganda, Rwanda, Tanzania)
- Personalized itinerary generation
- Route optimization using TSP algorithm
- User authentication and trip saving
- Responsive design with Premium Safari branding

