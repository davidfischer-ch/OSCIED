#!/usr/bin/env bash

#**********************************************************************************************************************#
#              OPEN-SOURCE CLOUD INFRASTRUCTURE FOR ENCODING AND DISTRIBUTION : SCRIPTS
#
#  Authors   : David Fischer
#  Contact   : david.fischer.ch@gmail.com
#  Project   : OSCIED (OS Cloud Infrastructure for Encoding and Distribution)
#  Copyright : 2012-2013 OSCIED Team. All rights reserved.
#**********************************************************************************************************************#
#
# This file is part of EBU/UER OSCIED Project.
#
# This project is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This project is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this project.
# If not, see <http://www.gnu.org/licenses/>
#
# Retrieved from https://github.com/ebu/OSCIED

set -o nounset # will exit if an unitialized variable is used

# Prevent importing N times the following (like C++ .h : #ifndef ... #endif)
if ! osciedCommonImported 2>/dev/null; then

# Constants ============================================================================================================

# FIXME Current implementation of orchestra doesn't accept external IP you must execute juju-menu.sh
# -> config to update storage's related constants automatically
STORAGE_PRIVATE_IP=''
STORAGE_MOUNTPOINT=''
STORAGE_BRICK=''
RELEASE='raring'      # Update this according to your needs
NETWORK_IFACE='eth0'  # Update this according to your needs

SCRIPTS_PATH=$(pwd)
BASE_PATH=$(dirname "$SCRIPTS_PATH")
CHARMS_PATH="$BASE_PATH/charms"
CHARMS_DEPLOY_PATH="$BASE_PATH/deploy/$RELEASE"
DOCS_PATH="$BASE_PATH/docs"
LIBRARY_PATH="$BASE_PATH/library"
MEDIAS_PATH="$BASE_PATH/medias"
SCENARIOS_PATH="$BASE_PATH/scenarios"
TEMPLATES_PATH="$BASE_PATH/templates"
TOOLS_PATH="$BASE_PATH/tools"
REFERENCES_PATH="$DOCS_PATH/references"

# Symbolic link to current configuration's path
SCENARIO_CURRENT_PATH="$SCENARIOS_PATH/current"
SCENARIO_CONFIG_FILE="$SCENARIO_CURRENT_PATH/config.yaml"

# Generated configuration
SCENARIO_GEN_PATH="$SCENARIO_CURRENT_PATH/generated"
SCENARIO_GEN_AUTHS_FILE="$SCENARIO_CURRENT_PATH/auths.list"
SCENARIO_GEN_IDS_FILE="$SCENARIO_CURRENT_PATH/ids.list"
SCENARIO_GEN_JSON_FILE="$SCENARIO_CURRENT_PATH/json.list"
SCENARIO_GEN_UNITS_FILE="$SCENARIO_CURRENT_PATH/units.list"

# Orchestra related configuration (e.g. initial setup)
SCENARIO_API_USERS_FILE="$SCENARIO_CURRENT_PATH/users.csv"
SCENARIO_API_MEDIAS_FILE="$SCENARIO_CURRENT_PATH/medias.csv"
SCENARIO_API_TPROFILES_FILE="$SCENARIO_CURRENT_PATH/tprofiles.csv"

# JuJu related configuration (e.g. environments)
SCENARIO_JUJU_ID_RSA="$SCENARIO_CURRENT_PATH/id_rsa"
SCENARIO_JUJU_ID_RSA_PUB="$SCENARIO_CURRENT_PATH/id_rsa.pub"
SCENARIO_JUJU_ENVS_FILE="$SCENARIO_CURRENT_PATH/environments.yaml"

# System configuration (e.g. certificates + juju configuration)
ID_RSA="$HOME/.ssh/id_rsa"
ID_RSA_PUB="$HOME/.ssh/id_rsa.pub"
JUJU_LOG="$BASE_PATH/juju-debug.log"
JUJU_PATH="$HOME/.juju"
JUJU_STORAGE_PATH="$JUJU_PATH/local/"
JUJU_ENVS_FILE="$JUJU_PATH/environments.yaml"


# Utilities ============================================================================================================

_check_config()
{
  if [ "$STORAGE_PRIVATE_IP" -a "$STORAGE_MOUNTPOINT" -a "$STORAGE_BRICK" ]; then
    echo ''
  elif [ $# -gt 0 ]; then
    echo '[DISABLED] '
  else
    xecho 'You must execute menu.sh config first'
  fi
}

_check_juju()
{
  if which juju > /dev/null; then
    echo ''
  elif [ $# -gt 0 ]; then
    echo '[DISABLED] '
  else
    xecho 'JuJu must be installed, this method is disabled'
  fi
}

_deploy_helper()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0).overwrite_helper scenario"
  fi
  scenario=$1

  techo "Deploy scenario $scenario"

  pecho 'Update symlink to current scenario'
  rm -f "$SCENARIO_CURRENT_PATH" 2>/dev/null
  ln -s "$scenario" "$SCENARIO_CURRENT_PATH" || xecho 'Unable to update symlink'

  pecho 'Initialize JuJu orchestrator configuration'
  if [ -f "$ID_RSA" ]; then
    suffix=$(md5sum "$ID_RSA" | cut -d' ' -f1)
    mecho "Backup certificate $ID_RSA into ${ID_RSA}_$suffix"
    cp -f "$ID_RSA"     "${ID_RSA}_$suffix"     || xecho 'Unable to backup certificate file (1/2)'
    cp -f "$ID_RSA_PUB" "${ID_RSA_PUB}_$suffix" || xecho 'Unable to backup certificate file (2/2)'
  fi
  if [ ! -f "$SCENARIO_JUJU_ID_RSA" ]; then
    recho 'It is strongly advised to create a certificate per scenario'
    yesOrNo $default 'generate it now'
    if [ $REPLY -eq $true ]; then
      ssh-keygen -t rsa -b 2048 -f "$SCENARIO_JUJU_ID_RSA"
    fi
  fi
  if [ -f "$SCENARIO_JUJU_ID_RSA" ]; then
    mecho "Using scenario's certificate file : $SCENARIO_JUJU_ID_RSA"
    # And make scenario's certificate the default
    cp -f "$SCENARIO_JUJU_ID_RSA"     "$ID_RSA"     || xecho 'Unable to copy certificate file (1/2)'
    cp -f "$SCENARIO_JUJU_ID_RSA_PUB" "$ID_RSA_PUB" || xecho 'Unable to copy certificate file (2/2)'
  fi
  # Fix ERROR SSH forwarding error: Agent admitted failure to sign using the key.
  ssh-add "$ID_RSA"

  # FIXME and what about *.pem stuff ?

  mkdir -p "$JUJU_PATH" "$JUJU_STORAGE_PATH" 2>/dev/null
  # Backup any already existing environments file (magic stuff) !
  if [ -f "$JUJU_ENVS_FILE" ]; then
    suffix=$(md5sum "$JUJU_ENVS_FILE" | cut -d' ' -f1)
    cp -f "$JUJU_ENVS_FILE" "${JUJU_ENVS_FILE}_$suffix" || xecho 'Unable to backup environments file'
  fi
  if [ -f "$SCENARIO_JUJU_ENVS_FILE" ]; then
    mecho "Using scenario's environments file : $SCENARIO_JUJU_ENVS_FILE"
    cp "$SCENARIO_JUJU_ENVS_FILE" "$JUJU_ENVS_FILE" || xecho 'Unable to copy environments file'
  else
    mecho 'Using juju to generate default environments file'
    juju generate-config -w || xecho "Unable to generate juju's environments file"
  fi
  $udo ufw disable # Fix master thesis ticket #80 - Juju stuck in pending when using LXC

  pecho "Copy JuJu environments file & SSH keys to Orchestra charm's deployment path"
  cp -f "$ID_RSA"         "$CHARMS_DEPLOY_PATH/oscied-orchestra/ssh/"
  cp -f "$ID_RSA_PUB"     "$CHARMS_DEPLOY_PATH/oscied-orchestra/ssh/"
  cp -f "$JUJU_ENVS_FILE" "$CHARMS_DEPLOY_PATH/oscied-orchestra/juju/"
  find "$JUJU_PATH" -mindepth 1 -maxdepth 1 -type f -name '*.pem' -exec cp -f {} \
    "$CHARMS_DEPLOY_PATH/oscied-orchestra/juju/" \;

  pecho "Execute script of scenario $scenario"
  $udo python "$scenario/scenario.py" "$(dirname "$CHARMS_DEPLOY_PATH")" -r "$RELEASE"
}

_overwrite_helper()
{
  if [ $# -ne 2 ]; then
    xecho "Usage: $(basename $0).overwrite_helper source destination"
  fi

  mkdir -p "$CHARMS_DEPLOY_PATH/$2" 2>/dev/null
  rsync -rtvh -LH --delete --progress --exclude='.git' --exclude='*.log' --exclude='*.pyc' \
    --exclude='celeryconfig.py' --exclude='build' --exclude='dist' --exclude='*.egg-info' \
    "$CHARMS_PATH/$1/" "$CHARMS_DEPLOY_PATH/$2/" || xecho "Unable to overwrite $2 charm"
}

_rsync_helper()
{
  if [ $# -ne 2 ]; then
    xecho "Usage: $(basename $0).rsync_publisher charm id"
  fi

  chmod 600 "$ID_RSA" || xecho 'Unable to find id_rsa certificate'

  _get_unit_public_url $true "$1" "$2"
  host="ubuntu@$REPLY"
  dest="/var/lib/juju/agents/unit-$1-$2/charm"
  ssh -i "$ID_RSA" "$host" -n "sudo chown 1000:1000 $dest -R"
  rsync -avhL --progress --delete -e "ssh -i '$ID_RSA'" --exclude=.git --exclude=config.json \
    --exclude=celeryconfig.py --exclude=*.pyc --exclude=local_config.pkl --exclude=charms \
    --exclude=ssh --exclude=environments.yaml --exclude=*.log "$CHARMS_PATH/$1/" "$host:$dest/"
  ssh -i "$ID_RSA" "$host" -n "sudo chown root:root $dest -R"
}

_standalone_execute_hook()
{
  if [ $# -ne 2 ]; then
    xecho "Usage: $(basename $0).standalone_execute_hook path hook"
  fi

  pecho 'Install juju-log & open-port tricks'
  if ! getInterfaceIPv4 "$NETWORK_IFACE" '4'; then
    xecho "Unable to detect network interface $NETWORK_IFACE IP address"
  fi
  ip=$REPLY
  $udo sh -c "cp -f $TEMPLATES_PATH/juju-log      $jujulog;  chmod 777 $jujulog"
  $udo sh -c "cp -f $TEMPLATES_PATH/open-port     $openport; chmod 777 $openport"
  $udo sh -c "cp -f $TEMPLATES_PATH/something-get $cget;     chmod 777 $cget"
  $udo sh -c "cp -f $TEMPLATES_PATH/something-get $rget;     chmod 777 $rget"
  $udo sh -c "cp -f $TEMPLATES_PATH/something-get $uget;     chmod 777 $uget"
  $udo sh -c "cp -f $TEMPLATES_PATH/something-get.list /tmp/;"
  $udo sh -c "sed -i 's:127.0.0.1:$ip:g' /tmp/something-get.list"
  pecho "Execute hook script $2"
  cd "$1"  || xecho "Unable to find path $1"
  $udo $2  || xecho 'Hook is unsucessful'
  recho 'Hook successful'
}

# Parse config.json of a actually running charm instance ! -------------------------------------------------------------

_get_unit_config()
{
  if [ $# -ne 3 ]; then
    xecho "Usage: $(basename $0).get_config_unit name number option"
  fi
  name=$1
  number=$2
  option=$3

  # Example : sS'storage_address' p29 S'ip-10-245-189-174.ec2.internal' p30
  chmod1="sudo chmod +rx /var/lib/juju/agents/unit-$name-$number/"
  chmod2="sudo chmod +rx /var/lib/juju/agents/unit-$name-$number/charm/"
  chmod3="sudo chmod +rx /var/lib/juju/agents/unit-$name-$number/charm/local_config.pkl"
  cat_local_config="cat /var/lib/juju/agents/unit-$name-$number/charm/local_config.pkl"
  val=$(juju ssh $name/$number "$chmod1; $chmod2; $chmod3; $cat_local_config" | tr '\n' ' ')
  REPLY=$(expr match "$val" ".*S'$option' p[0-9]\+ .'*\([^ ']*\)")
}

# Parse orchestra.yaml configuration file to get options value ---------------------------------------------------------

_get_root_secret()
{
  if [ -f "$SCENARIO_CONFIG_FILE" ]; then
    line=$(cat "$SCENARIO_CONFIG_FILE" | grep root_secret)
    root=$(expr match "$line" '.*"\(.*\)".*')
  else
    root='toto'
  fi
  [ ! "$root" ] && xecho 'Unable to detect root secret !'
  REPLY="$root"
}

_get_node_secret()
{
  if [ -f "$SCENARIO_CONFIG_FILE" ]; then
    line=$(cat "$SCENARIO_CONFIG_FILE" | grep node_secret)
    node=$(expr match "$line" '.*"\(.*\)".*')
  else
    node='abcd'
  fi
  [ ! "$node" ] && xecho 'Unable to detect node secret !'
  REPLY="$node"
}

# Parse charm's units URLs listing file to get specific URLs -----------------------------------------------------------

_get_units_dialog_listing()
{
  REPLY=$(cat "$SCENARIO_CONFIG_FILE" | sort | sed 's:=: :g;s:\n: :g')
  [ ! $REPLY ] && xecho 'Unable to generate units listing for dialog'
}

_get_services_dialog_listing()
{
  REPLY=$(cat "$SCENARIO_CONFIG_FILE" | sort | sed 's:/[0-9]*=: :g;s:\n: :g' | uniq)
  [ ! $REPLY ] && xecho 'Unable to generate services listing for dialog'
}

_get_unit_public_url()
{
  if [ $# -gt 3 ]; then
    xecho "Usage: $(basename $0).get_unit_public_url fail name (number)"
  fi
  fail=$1
  name=$2

  [ $# -eq 3 ] && number=$3 || number='.*'
  if [ -f "$SCENARIO_CONFIG_FILE" ]; then
    url=$(cat "$SCENARIO_CONFIG_FILE" | grep -m 1 "^$name/$number=" | cut -d '=' -f2)
  else
    url='127.0.0.1'
  fi
  [ ! "$url" -a $fail -eq $true ] && xecho "Unable to detect unit $1 public URL !"
  REPLY="$url"
}

_get_orchestra_url()
{
  if [ $# -eq 0 ]; then
    _get_unit_public_url $false 'oscied-orchestra'
  elif [ $# -eq 1 ]; then
    _get_unit_public_url $false 'oscied-orchestra' "$1"
  else
    xecho "Usage: $(basename $0).get_orchestra_url (number)"
  fi
  [ "$REPLY" ] && REPLY="http://$REPLY:5000"
}

_get_storage_uploads_url()
{
  REPLY="glusterfs://$STORAGE_PRIVATE_IP/$STORAGE_MOUNTPOINT/uploads"

}

_get_storage_medias_url()
{
  REPLY="glusterfs://$STORAGE_PRIVATE_IP/$STORAGE_MOUNTPOINT/medias"
}

_storage_upload_media()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0).storage_upload_media filename"
  fi

  _get_unit_public_url $true 'oscied-storage'
  host="ubuntu@$REPLY"
  bkp_path='/home/ubuntu/uploads'
  dst_path="$STORAGE_BRICK/uploads"
  chmod 600 "$ID_RSA" || xecho 'Unable to find id_rsa certificate'
  rsync -ah --progress --rsync-path='sudo rsync' -e "ssh -i '$ID_RSA'" "$1" "$host:$bkp_path/" || \
    xecho "Unable to copy media file to $bkp_path path in storage"
  ssh -i "$ID_RSA" "$host" -n "sudo rsync -ah --progress $bkp_path/ $dst_path/" || \
    xecho "Unable to synchronize ($dst_path->$dst_path) paths in storage"
  ssh -i "$ID_RSA" "$host" -n "sudo chown www-data:www-data $dst_path/ -R" || \
    xecho "Unable to set owner www-data for $dst_path path in storage"
  _get_storage_uploads_url
  REPLY="$REPLY/$(basename $1)"
}

# Save and get configuration from corresponding generated files --------------------------------------------------------

_save_auth()
{
  cat "$SCENARIO_GEN_AUTHS_FILE" 2>/dev/null | grep -v "^$1=" > /tmp/$$
  echo "$1=$2" >> /tmp/$$
  mv /tmp/$$ "$SCENARIO_GEN_AUTHS_FILE"
}

_get_auth()
{
  REPLY=$(cat "$SCENARIO_GEN_AUTHS_FILE" 2>/dev/null | grep "^$1=" | cut -d '=' -f2)
  [ ! "$REPLY" ] && xecho "Unable to detect $1 authentication"
}

_save_id()
{
  cat "$SCENARIO_GEN_IDS_FILE" 2>/dev/null | grep -v "^$1=" > /tmp/$$
  echo "$1=$2" >> /tmp/$$
  mv /tmp/$$ "$SCENARIO_GEN_IDS_FILE"
}

_get_id()
{
  REPLY=$(cat "$SCENARIO_GEN_IDS_FILE" 2>/dev/null | grep "^$1=" | cut -d '=' -f2)
  [ ! "$REPLY" ] && xecho "Unable to detect $1 ID"
}

_save_json()
{
  cat "$SCENARIO_GEN_JSON_FILE" 2>/dev/null | grep -v "^$1=" > /tmp/$$
  echo "$1=$2" >> /tmp/$$
  mv /tmp/$$ "$SCENARIO_GEN_JSON_FILE"
}

_get_json()
{
  REPLY=$(cat "$SCENARIO_GEN_JSON_FILE" 2>/dev/null | grep "^$1=" | cut -d '=' -f2)
  [ ! "$REPLY" ] && xecho "Unable to detect $1 json"
}

# Generate valid json strings of Orchestra API's objects ---------------------------------------------------------------

_json_user()
{
  if [ $# -ne 5 ]; then
    xecho "Usage: $(basename $0).json_user fname lname mail secret aplaftorm"
  fi

  a='admin_platform'
  JSON="{\"first_name\":\"$1\",\"last_name\":\"$2\",\"mail\":\"$3\",\"secret\":\"$4\",\"$a\":$5}"
}

_json_media()
{
  if [ $# -ne 3 ]; then
    xecho "Usage: $(basename $0).json_media uri vfilename title"
  fi

  JSON="{\"uri\":\"$1\",\"filename\":\"$2\",\"metadata\":{\"title\":\"$3\"}}"
}

_json_tprofile()
{
  if [ $# -ne 4 ]; then
    xecho "Usage: $(basename $0).json_tprofile title description encoder_name encoder_string"
  fi

  JSON="{\"title\":\"$1\",\"description\":\"$2\",\"encoder_name\":\"$3\",\"encoder_string\":\"$4\"}"
}

_json_ttask()
{
  d='metadata'
  m='media_in_id'
  p='profile_id'
  q='queue'
  t='title'
  v='filename'
  y='priority'
  if [ $# -ne 6 ]; then
    xecho "Usage: $(basename $0).json_ttask $m $p $v $t $q $y"
  fi

  JSON="{\"$m\":\"$1\",\"$p\":\"$2\",\"$v\":\"$3\",\"$d\":{\"$t\":\"$4\"},\"$q\":\"$5\",\"$y\":\"$6\"}"
}

_json_ptask()
{
  if [ $# -ne 3 ]; then
    xecho "Usage: $(basename $0).json_ttask media_id queue priority"
  fi

  JSON="{\"media_id\":\"$1\",\"queue\":\"$2\",\"priority\":\"$3\"}"
}

# Used to call / test Orchestra REST API -------------------------------------------------------------------------------

_test_api()
{
  if [ $# -ne 5 ]; then
    xecho "Usage: $(basename $0).test_api code method call user data"
  fi

  code=$1; m=$2; c=$3; u=$4; d=$5
  aa='Accept: application/json'
  ct='Content-type: application/json'
  if [ "$u" -a "$d" ]; then
    mecho "\nTest $code : $m $c auth: $u data: $d"
    result=$(curl -H "$aa" -H "$ct" -u "$u" -d "$d" -X "$m" "$c" --write-out %{http_code})
  elif [ "$u" ]; then
    mecho "\nTest $code : $m $c auth: $u"
    result=$(curl -H "$aa" -H "$ct" -u "$u" -X "$m" "$c" --write-out %{http_code})
  elif [ "$d" ]; then
    mecho "\nTest $code : $m $c data: $d"
    result=$(curl -H "$aa" -H "$ct" -d "$d" -X "$m" "$c" --write-out %{http_code})
  else
    mecho "\nTest $code : $m $c"
    result=$(curl -H "$aa" -H "$ct" -X "$m" "$c" --write-out %{http_code})
  fi
  echo $result
  if ! echo "$result" | grep -q "$code\$"; then
    xecho "Test $m $c failed with code : $result"
  fi
  echo
  anum='0-9a-zA-Z'
  regex=".*\"\([$anum]\{8\}-[$anum]\{4\}-[$anum]\{4\}-[$anum]\{4\}-[$anum]\{12\}\)\".*"
  ID=$(expr match "$result" "$regex")
}

osciedCommonImported()
{
  echo > /dev/null
}
fi
# START OF LOGICIELS UBUNTU UTILS (licencing : LogicielsUbuntu project's licence)
# Retrieved from:
#   git clone https://github.com/davidfischer-ch/logicielsUbuntu.git

# Prevent importing N times the following (like C++ .h : #ifndef ... #endif)
if ! logicielsUbuntuUtilsImported 2>/dev/null; then

# Colored echoes and yes/no question ===============================================================

true=0
false=1
true_auto=2
false_auto=3

if [ -t 0 ]; then
  TXT_BLD=$(tput bold)
  TXT_BLK=$(tput setaf 0)
  TXT_RED=$(tput setaf 1)
  TXT_GREEN=$(tput setaf 2)
  TXT_YLW=$(tput setaf 3)
  TXT_BLUE=$(tput setaf 4)
  TXT_PURPLE=$(tput setaf 5)
  TXT_CYAN=$(tput setaf 6)
  TXT_WHITE=$(tput setaf 7)
  TXT_RESET=$(tput sgr0)

  TECHO_COLOR=$TXT_GREEN
  PECHO_COLOR=$TXT_BLUE
  MECHO_COLOR=$TXT_YLW
  CECHO_COLOR=$TXT_YLW
  RECHO_COLOR=$TXT_PURPLE
  QECHO_COLOR=$TXT_CYAN
  XECHO_COLOR=$TXT_RED
else
  TXT_BLD=''
  TXT_BLK=''
  TXT_RED=''
  TXT_GREEN=''
  TXT_YLW=''
  TXT_BLUE=''
  TXT_PURPLE=''
  TXT_CYAN=''
  TXT_WHITE=''
  TXT_RESET=''

  TECHO_COLOR='[TITLE] '
  PECHO_COLOR='[PARAGRAPH] '
  MECHO_COLOR='[MESSAGE] '
  CECHO_COLOR='[CODE] '
  RECHO_COLOR='[REMARK] '
  QECHO_COLOR='[QUESTION] '
  XECHO_COLOR=''
fi

if echo "\n" | grep -q 'n'
then e_='-e'
else e_=''
fi

# By default output utility is the well known echo, but you can use juju-log with ECHO='juju-log'
echo=${ECHO:=echo}

# Disable echo extra parameter if output utility is not echo
[ "$echo" != 'echo' ] && e_=''

#if [ -z $DISPLAY ]
#then DIALOG=dialog
#else DIALOG=Xdialog
#fi
DIALOG=dialog

techo() { $echo $e_ "$TECHO_COLOR$TXT_BLD$1$TXT_RESET"; } # script title
pecho() { $echo $e_ "$PECHO_COLOR$1$TXT_RESET";         } # text title
mecho() { $echo $e_ "$MECHO_COLOR$1$TXT_RESET";         } # message (text)
cecho() { $echo $e_ "$CECHO_COLOR> $1$TXT_RESET";       } # message (code)
recho() { $echo $e_ "$RECHO_COLOR$1 !$TXT_RESET";       } # message (remark)
qecho() { $echo $e_ "$QECHO_COLOR$1 ?$TXT_RESET";       } # message (question)
becho() { $echo $e_ "$TXT_RESET$1";                     } # message (reset)

xecho() # message (error)
{
  [ $# -gt 1 ] && code=$2 || code=1
  $echo $e_ "${XECHO_COLOR}[ERROR] $1 (code $code)$TXT_RESET" >&2
  pause
  exit $code
}

pause() # menu pause
{
  [ ! -t 0 ] && return # skip if non interactive
  $echo $e_ 'press any key to continue ...'
  read ok </dev/tty
}

readLine() # menu read
{
  qecho "$1"
  read CHOICE </dev/tty
}

# use sudo only if we're not root & if available
if [ "$(id -u)" != '0' -a "$(which sudo)" != '' ]
then udo='sudo'
else udo=''
fi

service="$udo service"
if ! which service > /dev/null; then
  service() # replace missing 'service' binary !
  {
    if [ $# -ne 2 ]; then
      xecho "Usage: $(basename $0).service name argument"
    fi
    $udo /etc/init.d/$1 $2
  }
fi

if which apt-get > /dev/null; then
  installPack="$udo dpkg -i"
  install="$udo apt-get -fyq --force-yes install"
  buildDep="$udo apt-get -fyq --force-yes build-dep"
  update="$udo apt-get -fyq --force-yes update"
  upgrade="$udo apt-get -fyq --force-yes upgrade"
  distupgrade="$udo apt-get -fyq --force-yes dist-upgrade"
  remove="$udo apt-get -fyq --force-yes remove"
  autoremove="$udo apt-get -fyq --force-yes autoremove"
  purge="$udo apt-get -fyq --force-yes purge"
  key="$udo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys"
  packages="dpkg --get-selections"
elif which ipkg > /dev/null; then
  installPack="$udo ipkg install"
  install="$udo ipkg install"
  buildDep="xecho 'buildDep not implemented' #"
  update="$udo ipkg update"
  upgrade="$udo ipkg upgrade"
  distupgrade="$udo ipkg upgrade"
  remove="$udo ipkg remove"
  autoremove="xecho 'autoremove not implemented' #"
  purge="$udo ipkg remove"
  key="xecho 'key not implemented'"
  packages="xecho 'packages not implemented'"
else
  xecho 'Unable to find apt-get nor ipkg in your system'
fi

#if ! pushd . 2>/dev/null; then
#  recho 'pushd/popd as internal functions'
#  dirLifo=''
#  pushd()
#  {
#    if [ $# -ne 1 ]; then
#      xecho "Usage: $(basename $0).pushd path"
#    fi
#    dirLifo="$(pwd):$dirLifo"
#    cd "$1"
#  }
#  popd()
#  {
#    dir=$(echo $dirLifo | cut -d ':' -f1)
#    dirLifo=$(echo $dirLifo | cut -d ':' -f2-)
#    if [ "$dir" ]; then
#      cd "$dir"
#    else
#      xecho 'Paths LIFO is empty !'
#    fi
#  }
#else
#  recho 'pushd/popd as shell built-in'
#  popd
#fi

# unit-testing of the implementation !
#pushdTest()
#{
#  pushdUnitFailed="pushd/popd unit test failed !"
#  here=$(pwd)
#  pushd /media && echo $dirLifo
#  if [ "$(pwd)" != '/media' ]; then xecho "$pushdUnitFailed 1/5"; fi
#  cd /home
#  pushd /bin && echo $dirLifo
#  if [ "$(pwd)" != '/bin' ]; then xecho "$pushdUnitFailed 2/5"; fi
#  popd && echo $dirLifo
#  if [ "$(pwd)" != '/home' ]; then xecho "$pushdUnitFailed 3/5 $(pwd)"; fi
#  popd && echo $dirLifo
#  if [ "$(pwd)" != "$here" ]; then xecho "$pushdUnitFailed 4/5"; fi
#}

# Asks user to confirm an action (with yes or no) --------------------------------------------------
#> 0 (true value for if [ ]) if yes, 1 if no and (defaultChoice) by default
#1 : default (0 = yes / 1 = no)
#2 : question (automatically appended with [Y/n] ? / [y/N] ?)
yesOrNo()
{
  if [ $# -ne 2 ]; then
    xecho "Usage : yesOrNo default question\n\tdefault : 0=yes or 1=no 2='force yes' 3='force no'"
  fi

  local default="$1"
  local question="$2"
  case $default in
  "$true"       ) qecho "$question [Y/n]";;
  "$false"      ) qecho "$question [y/N]";;
  "$true_auto"  ) REPLY=$true;  return $true ;;
  "$false_auto" ) REPLY=$false; return $true ;;
  * ) xecho "Invalid default value : $default";;
  esac

  while true; do
    read REPLY </dev/tty
    case "$REPLY" in
    '' ) REPLY=$default ;;
    'y' | 'Y' ) REPLY=$true  ;;
    'n' | 'N' ) REPLY=$false ;;
    * ) REPLY='' ;;
    esac
    if [ "$REPLY" ]; then break; fi
    default='' # cancel default value
    recho "Please answer y for yes or n for no"
  done
}

# Utilities ========================================================================================

threadsCount()
{
  grep -c ^processor /proc/cpuinfo
}

# Checkout a subversion repository locally ---------------------------------------------------------
# TODO
checkout()
{
  [ $# -ne 4 ] && return $false

  rm -rf $2 2>/dev/null
  svn checkout --username=$3 --password=$4 --non-interactive --trust-server-cert $1 $2
}

# Generate a random password -----------------------------------------------------------------------
# size      : number of characters; defaults to 32
# special   : include special characters
# lowercase : convert any characters to lower case
# uppercase : convert any characters to upper case
randpass()
{
  [ $# -ne 4 ] && echo ''

  [ $2 -eq $true ] && chars='[:graph:]' || chars='[:alnum:]'
  [ $3 -eq $true ] && lower='[:upper:]' || lower='[:lower:]'
  [ $4 -eq $true ] && upper='[:lower:]' || upper='[:upper:]'
  cat /dev/urandom | tr -cd "$chars" | head -c $1 | \
    tr '[:upper:]' "$lower" | tr '[:lower:]' "$upper"
}

# Add a repository if it isn't yet listed in sources.list ------------------------------------------
# repositoryName   : the name (eg : virtualbox) of the repo.
# repositoryDebUrl : the debian URL (http://...) of the repo.
# repositoryKind   : the kind (contrib, ...) of the repo.
addAptRepo()
{
  if [ $# -ne 3 ]; then
    xecho 'Usage : addAptRepo repositoryName repositoryDebUrl repositoryKind'
  fi

  local release="$(lsb_release -cs)"
  if [ ! -f "/etc/apt/sources.list.d/$1.list" ]; then
    $udo sh -c "echo 'deb $2 $release $3' >> '/etc/apt/sources.list.d/$1.list'"
  fi
}

# Add a 'ppa' repository trying to fix TODO --------------------------------------------------------
# repositoryPpa : the PPA (eg : ppa:rabbitvcs/ppa) of the repo.
# repositoryName : the PPA name without ppa:/... TODO
addAptPpaRepo()
{
  if [ $# -ne 2 ]; then
    xecho 'Usage : addAptPpaRepo repositoryPpa repositoryName'
  fi

  local repositoryPpa="$1"
  local repositoryName="$2"

  local ok=$false
  local here="$(pwd)"
  local last="$(lsb_release -cs)"
  cd /etc/apt/sources.list.d
  $udo rm -rf *$repositoryName*
  $udo apt-add-repository -y $repositoryPpa
  repositoryFile=$(ls | grep $repositoryName)
  if [ ! "$repositoryFile" ]; then
    xecho "Unable to find $repositoryName's repository file"
  fi
  mecho "Repository file : $repositoryFile"
  for actual in "$last" 'quantal' 'precise' 'oneiric' 'maverick' 'lucid'
  do
    $udo sh -c "sed -i -e 's:$last:$actual:g' $repositoryFile"
    mecho "Checking if the $repositoryName's repository does exist for $actual ..."
    if $update 2>&1 | grep -q $repositoryName; then
      mecho "Hum, the $repositoryName's repository does not exist for $actual"
      recho "Ok, trying the next one"
    else
      ok=$true
      break
    fi
    last=$actual
  done
  cd "$here"
  if [ $ok -eq $true ]
  then mecho "Using the $repositoryName's repository for $actual"
  else xecho 'Unable to find a suitable repository !'
  fi
}

# Add a GPG key to the system ----------------------------------------------------------------------
# gpgKeyUrl : the URL (deb http://....asc) of the GPG key
addGpgKey()
{
  if [ $# -ne 1 ]; then
    xecho 'Usage : addGpgKey gpgKeyUrl'
  fi

  wget -q "$1" -O- | $udo apt-key add -
}

# Check if a package is installed ------------------------------------------------------------------
# packageName : name of the package to check
isInstalled()
{
  if [ $# -ne 1 ]; then
    xecho 'Usage : isInstalled packageName'
  fi

  if $packages | grep $1 | grep -v -q 'deinstall'
  then return $true
  else return $false
  fi
}

# Install a package if it isn't yet installed ------------------------------------------------------
# packageName : name of the package to install
# binaryName  : name of the binary to find
autoInstall()
{
  if [ $# -ne 2 ]; then
    xecho 'Usage : autoInstall packageName binaryName'
  fi

  local packageName="$1"
  local binaryName="$2"

  # install the package if missing
  if which "$binaryName" > /dev/null; then
    recho "Binary $binaryName of package $packageName founded, nothing to do"
  else
    recho "Binary $binaryName of package $packageName missing, installing it"
    eval $install $packageName || xecho "Unable to install package $packageName !"
  fi
}

# Install a package if it isn't yet installed ------------------------------------------------------
# libName : name of the package to install (library)
autoInstallLib()
{
  if [ $# -ne 1 ]; then
    xecho 'Usage : autoInstallLib libName'
  fi

  # install the libs package if missing
  if dpkg --get-selections | grep "$1" | grep -q install; then
    recho "Library $1 founded, nothing to do"
  else
    recho "Library $1 missing, installing it"
    eval $install $1
  fi
}

# Install a package (with a setup method) if it isn't yet installed --------------------------------
# setupName  : name of the (setup) method to execute
# binaryName : name of the binary to find
autoInstallSetup()
{
  if [ $# -ne 2 ]; then
    xecho 'Usage : autoInstallSetup setupName binaryName'
  fi

  local setupName="$1"
  local binaryName="$2"

  # install the package if missing
  if which "$binaryName" > /dev/null; then
    recho "Binary $binaryName of setup $setupName founded, nothing to do"
  else
    recho "Binary $binaryName of setup $setupName missing, installing it"
    $setupName
  fi
}

# Extract a debian package -------------------------------------------------------------------------
debianDepack()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0) debianFilename"
  fi

  local name=$(basename "$1" .deb)
  dpkg-deb -x "$1" "$name"
  mkdir "$name/DEBIAN"
  dpkg-deb -e "$1" "$name/DEBIAN"
}

# Create a debian package of a folder --------------------------------------------------------------
debianRepack()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0) debianPath"
  fi

  dpkg-deb -b "$1"
}

checkDepend()
{
  if [ $# -ne 1 ]; then
    xecho 'Usage : checkDepend binaryName methodName'
  fi

  if ! which "$1" > /dev/null; then
    xecho "Dependency : $2 depends of $1, unable to find $1"
  fi
}

validateNumber()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0).validateNumber input"
  fi
  [ "$1" -eq "$1" 2>/dev/null ]
}

# Get the Nth first digits of the IPv4 address of a network interface ------------------------------
#> The address, ex: 192.168.1.34 -> [3 digits] 192.168.1. [1 digit] 192.
# ethName : name of the network interface to get ...
# numberOfDigitsRequired : number of digits to return (1-4)
getInterfaceIPv4()
{
  if [ $# -ne 2 ]; then
    xecho 'Usage : getInterfaceIPv4 ethName numberOfDigitsRequired'
  fi

  local ethName="$1"
  local numberOfDigitsRequired="$2"

  # find the Nth first digits of the ip address of a certain network interface,
  # this method use regular expression to filter the output of ifconfig
  cmd=$(ifconfig $ethName)
  case "$numberOfDigitsRequired" in
  '1' ) REPLY=$(expr match "$cmd" '.*inet ad\+r:\([0-9]*\.\)[0-9]*\.[0-9]*\.[0-9]*');;
  '2' ) REPLY=$(expr match "$cmd" '.*inet ad\+r:\([0-9]*\.[0-9]*\.\)[0-9]*\.[0-9]*');;
  '3' ) REPLY=$(expr match "$cmd" '.*inet ad\+r:\([0-9]*\.[0-9]*\.[0-9]*\.\)[0-9]*');;
  '4' ) REPLY=$(expr match "$cmd" '.*inet ad\+r:\([0-9]*\.[0-9]*\.[0-9]*\.[0-9]*\)');;
  * ) xecho 'numberOfDigitsRequired must be between 1 and 4' ;;
  esac

  # FIXME : check du parsing !
}

# Get the name of the default network interface ----------------------------------------------------
getDefaultInterfaceName()
{
  local default="$(route | grep ^default)"
  REPLY=$(expr match "$default" '.* \(.*\)$')
  if [ ! "$REPLY" ]; then
    xecho '[BUG] Unable to detect default network interface'
  fi
}

validateIP()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0).validateIP ip"
  fi
  [ $(echo $1 | sed -n "/^[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*$/p") ]
}

validateMAC()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0).validateMAC mac"
  fi
  [ $(echo $1 | sed -n "/^\([0-9A-Za-z][0-9A-Za-z]:\)\{5\}[0-9A-Za-z][0-9A-Za-z]$/p") ]
}

# Set setting value of a 'JSON' configuration file -------------------------------------------------
# TODO parameters comment
setSettingJSON_STRING()
{
  if [ $# -ne 3 ]; then
    xecho "Usage: $(basename $0).setSettingJSON file name value"
  fi

  sed  -i "s<\"$2\" *: *\"[^\"]*\"<\"$2\": \"$3\"<g" "$1"
  grep -q "\"$2\": \"$3\"" "$1"
}

# Set setting value of a 'JSON' configuration file -------------------------------------------------
# TODO parameters comment
setSettingJSON_BOOLEAN()
{
  if [ $# -ne 3 ]; then
    xecho "Usage: $(basename $0).setSettingJSON file name value"
  fi

  [ $3 -eq $true ] && value='true' || value='false'
  sed  -i "s<\"$2\" *: *[a-zA-Z]*<\"$2\": $value<g" "$1"
  grep -q "\"$2\": $value" "$1"
}

# Set setting value of a 'BASH' configuration file -------------------------------------------------
# TODO parameters comment
setSettingBASH()
{
  if [ $# -ne 3 -a $# -ne 4 ]; then
    xecho "Usage: $(basename $0).setSettingBASH file enabled name [value]"
  fi

  local toggle=''
  if [ $2 -eq $false ]; then toggle='#'; fi
  if [ $# -eq 3 ]; then
    sed  -i "s<[# \t]*$3<$toggle$3<" "$1"
    grep -q "$toggle$3" "$1"
  elif [ $# -eq 4 ]; then
    sed  -i "s<[# \t]*$3[ \t]*=.*<$toggle$3=$4<" "$1"
    grep -q "$toggle$3=$4" "$1"
  fi
}

# Set setting value of a 'htaccess' file -----------------------------------------------------------
# TODO parameters comments
setSettingHTA()
{
  if [ $# -ne 3 -a $# -ne 4 ]; then
    xecho "Usage: $(basename $0).setSettingHTA file enabled name [value]"
  fi

  local toggle=''
  if [ $2 -eq $false ]; then toggle='#'; fi
  if [ $# -eq 3 ]; then
    sed  -i "s<[# \t]*$3<$toggle$3<" "$1"
    grep -q "$toggle$3" "$1"
  elif [ $# -eq 4 ]; then
    sed  -i "s<[# \t]*$3[ \t]*.*<$toggle$3 $4<" "$1"
    grep -q "$toggle$3 $4" "$1"
  fi
}

# Set setting value of a 'PHP' configuration file --------------------------------------------------
# TODO parameters comments
setSettingPHP()
{
  if   [ $# -eq 4 ]; then key="\$$2\['$3'\]";         value=$4
  elif [ $# -eq 5 ]; then key="\$$2\['$3'\]\['$4'\]"; value=$5
  else xecho "Usage: $(basename $0).setSettingPHP file variable (category) name value"
  fi

  sed  -i "s<$key = .*<$key = '$value';<" "$1"
  grep -q "$key = '$value';" "$1"
}

screenRunning()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0).screenRunning name"
  fi
  screen -list | awk '{print $1}' | grep -q "$1"
}

screenLaunch()
{
  if [ $# -lt 2 ]; then
    xecho "Usage: $(basename $0).screenLaunch name command"
  fi
  screen -dmS "$@"
}

screenKill()
{
  if [ $# -ne 1 ]; then
    xecho "Usage: $(basename $0).screenKill name"
  fi
  screen -X -S "$1" kill
}

# http://freesoftware.zona-m.net/how-automatically-create-opendocument-invoices-without-openoffice

# Apply sed in a [Libre|Open] Office document ------------------------------------------------------
# oooSrcFilename : name of the source [Libre|Open] office file
# oooDstFilename : name of the destination [Libre|Open] office file
# paramsFilename : name of the params file (a couple of param value by line)
oooSed()
{
  if [ $# -ne 3 ]; then
    xecho 'Usage : oooSed oooSrcFilename oooDstFilename paramsFilename'
  fi

  local work_dir='/tmp/OOO_SED'
  local oooSrcFilename="$1"
  local oooDstFilename="$2"
  local paramsFilename="$3"

  mecho "Apply sed in a [Libre|Open] Office document"
  mecho "Source         : $oooSrcFilename"
  mecho "Destination    : $oooDstFilename"
  mecho "Sed parameters : $paramsFilename"

  rm -rf $work_dir
  mkdir  $work_dir
  # FIXME local filename instead of filename, + test behaviour !
  filename=$(basename $oooSrcFilename)
  filename=$(echo ${filename%.*})

  cp $oooSrcFilename $work_dir/my_template
  cp $paramsFilename $work_dir/my_data.sh

  # preparation
  cd     $work_dir
  mkdir  work
  mv     my_template work
  cd     work
  unzip  my_template > /dev/null
  rm     my_template

  # replace text strings
  local content="$(cat content.xml)"
  local styles="$(cat styles.xml)"

  # parse params list line by line to find
  #          param value
  while read param value
  do
    if [ "$read$param" ]; then
      echo "s#$param#$value#g"
      content=$(echo $content | sed "s#$param#$value#g")
      styles=$(echo $styles | sed "s#$param#$value#g")
    fi
  done < ../my_data.sh # redirect done before while loop

  rm -f content.xml
  echo "$content" > content.xml

  rm -f styles.xml
  echo "$styles" > styles.xml

  # zip everything, rename it as .od* file and clean up
  find . -type f -print0 | xargs -0 zip ../$filename > /dev/null
  cd ..
  mv ${filename}.zip $oooDstFilename
  cd ..
  rm -rf $work_dir
}

# http://dag.wieers.com/home-made/unoconv/

# Convert a [Libre|Open] office document to a PDF with unoconv -------------------------------------
# oooSrcFilename : name of the [Libre|Open] office document to convert
oooToPdf()
{
  if [ $# -ne 3 ]; then
    xecho 'Usage : oooToPdf oooSrcFilename'
  fi

  unoconv -v --format pdf $1
}

logicielsUbuntuUtilsImported()
{
  echo > /dev/null
}
fi

# END OF LOGICIELS UBUNTU UTILS
