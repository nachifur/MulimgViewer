class PythonMulimgviewer < Formula
  include Language::Python::Virtualenv

  desc "A multi-image viewer that can open multiple images in one interface"
  homepage "https://mulimgviewer.readthedocs.io/"
  url "https://files.pythonhosted.org/packages/source/m/mulimgviewer/mulimgviewer-3.9.10.tar.gz"
  sha256 "b2b060a27effcab6ef57a9b4126ebb8a203528ba3a6f641326337bf3a6d921c9"
  license "GPLv3"
  head "https://github.com/nachifur/MulimgViewer", branch: "master"
  depends_on "python@3.11"
  depends_on "wxpython"
  depends_on "pillow"

  resource "piexif" do
    url "https://github.com/hMatoba/Piexif/archive/1.0.13.tar.gz"
    sha256 "66278d77ffa8fc816736104bc8bf5d26ac95cb8b9b3420e17f6d6d9a475e1e43"
  end

  resource "requests" do
    url "https://github.com/psf/requests/archive/v2.28.2/python-requests-2.28.2.tar.gz"
    sha256 "375d6bb6b73af27c69487dcf1df51659a8ee7428420caff21253825fb338ce10"
  end

  def install
    virtualenv_install_with_resources
  end
end
