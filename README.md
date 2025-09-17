# AnesysIQ Backend

## Overview

AnesysIQ is an evidence-based decision support system for personalized anesthesia induction planning. The system integrates pharmacogenetic testing, clinical risk factors, and published literature to provide individualized drug selection and dosing recommendations for anesthetic agents.

This repository contains the backend API for the AnesysIQ system, built with Django and Django REST Framework.

## Features

- **Patient Data Management**: Comprehensive patient profiling with clinical and genetic parameters
- **Route Selection Engine**: Intelligent selection between Intravenous (IV) and Inhalation routes
- **Agent Selection System**: Multi-agent assessment for IV agents (Propofol, Etomidate, Ketamine) and volatile agents
- **Personalized Dosing Calculator**: Pharmacokinetic and pharmacodynamic adjustments based on genetics and clinical factors
- **Risk Assessment & Visualization**: Dose-response curve modeling and probability calculations
- **RESTful API**: Well-documented API endpoints for frontend integration

## Installation

### Prerequisites

- Python 3.8 or higher
- pip or pipenv for dependency management
- Git

### Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Faerque/anesysiq-backend.git
   cd anesysiq-backend
   ```

2. **Install dependencies:**

   Using pip:

   ```bash
   pip install -r requirements.txt
   ```

   Or using pipenv:

   ```bash
   pipenv install
   pipenv shell
   ```

3. **Apply database migrations:**

   ```bash
   python manage.py migrate
   ```

4. **Create a superuser (optional):**

   ```bash
   python manage.py createsuperuser
   ```

5. **Run the development server:**

   ```bash
   python manage.py runserver
   ```

The API will be available at `http://127.0.0.1:8000/`

## Usage

### API Endpoints

The backend provides RESTful API endpoints for:

- Patient data management
- Route and agent selection
- Dosing calculations
- Risk assessment

For detailed API documentation, see [API_DOCUMENTATION.md](API_DOCUMENTATION.md)

### Example Usage

```python
import requests

# Example API call
response = requests.post('http://127.0.0.1:8000/api/patients/',
                        json={'name': 'John Doe', 'age': 45, ...})
```

## Project Structure

```text
backend_AnesysIQ/          # Django project settings
├── __init__.py
├── asgi.py
├── settings.py
├── urls.py
└── wsgi.py

process_data/              # Main app for data processing
├── migrations/           # Database migrations
├── models.py            # Data models
├── serializers.py       # API serializers
├── views.py             # API views
├── urls.py              # URL patterns
└── tests.py             # Unit tests

data/                     # Generated data and plots
manage.py                 # Django management script
requirements.txt          # Python dependencies
Pipfile                   # Pipenv dependencies
```

## Development

### Running Tests

```bash
python manage.py test
```

### Code Style

This project follows PEP 8 style guidelines. Use tools like `black` and `flake8` for code formatting and linting.

### Database

The project uses SQLite for development. For production, configure PostgreSQL or another database in `settings.py`.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Based on research in pharmacogenetics and anesthesia
- Uses evidence-based algorithms from published literature
- Developed as part of thesis work on personalized medicine

## Contact

For questions or support, please open an issue on GitHub.

---

For detailed technical documentation on how the system works, see [README_how_it_works.md](README_how_it_works.md)
