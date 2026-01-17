pid_file = "/home/vault/pidfile"

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path   = "/home/vault/auth/role_id"
      secret_id_file_path = "/home/vault/auth/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }

  sink "file" {
    config = {
      path = "/home/vault/token"
    }
  }
}

vault {
  address = "http://truckerp-vault:8200"
}

template {
  source      = "/home/vault/templates/truckerp.env.tpl"
  destination = "/home/vault/rendered_host/truckerp.env"
  perms       = "0640"
}
