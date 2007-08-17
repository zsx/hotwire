%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%{!?python_sitearch: %define python_sitearch %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1)")}

Summary: Hotwire Shell
Name: hotwire
Version: 0.567
Release: 1
Source0: http://hotwire-shell.googlegroups.com/web/hotwire-%{version}.zip
License: GPL
Group: User Interface/Desktops
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch
Url: http://submind.verbum.org/hotwire
BuildRequires: python-devel
Requires: pygtk2
Requires: gnome-python2-desktop
Requires: desktop-file-utils

%description
Interactive hybrid text/graphical shell for developers and
system administrators

%prep
%setup -q

%build
python setup.py build

%install
rm -rf $RPM_BUILD_ROOT
python setup.py install --no-compile --root=$RPM_BUILD_ROOT

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root)
%doc COPYING README
%{_bindir}/hotwire
%dir %{python_sitelib}/hotwire
%{python_sitelib}/hotwire/*
%dir %{python_sitelib}/hotwire_ui
%{python_sitelib}/hotwire_ui/*
%{_datadir}/applications/hotwire.desktop

%post
desktop-file-install --vendor='hotwire' %{_datadir}/applications/hotwire.desktop 

%changelog
* Thu May 25 2007 Colin Walters <walters@redhat.com> - 0.450-1
- Initial fedora package.

