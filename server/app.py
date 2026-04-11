import uvicorn
from app.main import app  # noqa: F401


def main():
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, workers=1)


if __name__ == "__main__":
    main()
