#!/usr/bin/env bash
# Instala pacotes do apt no runner do CI: `bash tools/apt_no_ci.sh <pacote>...`.
#
# Em 11/11/2026 o DNS de *.ubuntu.com sumiu dos runners do GitHub por horas
# (`Temporary failure resolving 'security.ubuntu.com'`) e todo job do backend
# caía no apt, inclusive na main. Quando os mirrors do Ubuntu não resolvem, o
# script troca as fontes do apt por um mirror de fora da Canonical e instala de
# lá. Com o DNS normal, o caminho é o de sempre.
set -uo pipefail

instalar() {
  sudo apt-get update -qq && sudo apt-get install -y -qq "$@"
}

resolve() {
  timeout 15 getent hosts "$1" >/dev/null
}

if resolve security.ubuntu.com && resolve archive.ubuntu.com; then
  instalar "$@" && exit 0
fi

for mirror in http://mirrors.edge.kernel.org/ubuntu http://mirror.math.princeton.edu/pub/ubuntu; do
  echo "::warning::apt: mirrors do Ubuntu fora do ar; instalando de $mirror"
  sudo sed -i -E "s#^URIs:.*#URIs: $mirror/#" /etc/apt/sources.list.d/ubuntu.sources
  instalar "$@" && exit 0
done
exit 1
