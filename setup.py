
import re
import setuptools


def get_version(path="src/nmea_converter_proxy/__init__.py"):
    """ Return the version of by with regex intead of importing it"""
    init_content = open(path, "rt").read()
    pattern = r"^__version__ = ['\"]([^'\"]*)['\"]"
    return re.search(pattern, init_content, re.M).group(1)


def get_requirements(path):

    setuppy_format = \
        'https://github.com/{user}/{repo}/tarball/master#egg={egg}'

    setuppy_pattern = \
        r'github.com/(?P<user>[^/.]+)/(?P<repo>[^.]+).git#egg=(?P<egg>.+)'

    dep_links = []
    install_requires = []
    with open(path) as f:
        for line in f:

            if line.startswith('-e'):
                url_infos = re.search(setuppy_pattern, line).groupdict()
                dep_links.append(setuppy_format.format(**url_infos))
                egg_name = '=='.join(url_infos['egg'].rsplit('-', 1))
                install_requires.append(egg_name)
            else:
                install_requires.append(line.strip())

    return install_requires, dep_links


requirements, dep_links = get_requirements('requirements.txt')
dev_requirements, dev_dep_links = get_requirements('dev-requirements.txt')

setuptools.setup(name='nmea_converter_proxy',
                 version=get_version(),
                 description="TCP proxy forwarding ASCII messages to an NMEA concentrator",
                 long_description=open('README.rst').read().strip(),
                 author="Kevin Samuel",
                 author_email="kevin.samuel@yandex.com",
                 url='https://github.com/ksamuel/nmea_converter_proxy/',
                 packages=setuptools.find_packages('src'),
                 package_dir={'': 'src'},
                 install_requires=requirements,
                 extras_require={
                     'dev': dev_requirements
                 },
                 setup_requires=['pytest-runner'],
                 tests_require=dev_requirements,
                 include_package_data=True,
                 license='MIT',
                 zip_safe=False,
                 keywords='nmea_converter_proxy',
                 classifiers=['Development Status :: 1 - Planning',
                              'Intended Audience :: Developers',
                              'Natural Language :: English',
                              'Programming Language :: Python :: 3.5',
                              'Programming Language :: Python :: 3 :: Only',
                              'Management',
                              'Operating System :: OS Independent',
                              'License :: OSI Approved :: MIT License'],)
