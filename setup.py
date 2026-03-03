from setuptools import setup


setup(
    name="model-console",
    version="0.1.0",
    description="Local-first role-agnostic model orchestration loops",
    packages=["model_console"],
    install_requires=[
        "PyYAML>=6.0",
        "jsonschema>=4.22",
    ],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "mc=model_console.cli:main",
        ]
    },
)
