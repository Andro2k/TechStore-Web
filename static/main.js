function prepararEdicion(id, nombre, marca, precio, stock) {
    // Llenar los campos del modal
    document.getElementById('edit_id').value = id;
    document.getElementById('edit_nombre').value = nombre;
    document.getElementById('edit_marca').value = marca;
    document.getElementById('edit_precio').value = precio;
    document.getElementById('edit_stock').value = stock;

    // Mostrar el modal (usando Bootstrap)
    var myModal = new bootstrap.Modal(document.getElementById('editModal'));
    myModal.show();
}

document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');
    const toggleBtn = document.getElementById('sidebarToggle');

    if (toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            sidebar.classList.toggle('collapsed');
            mainContent.classList.toggle('expanded');
        });
    }

    // 1. Manejo del cambio de sucursal automático
    const selectSucursal = document.getElementById('sucursalSelector');
    if (selectSucursal) {
        selectSucursal.addEventListener('change', function() {
            this.form.submit();
        });
    }

    // 2. Confirmación antes de agregar un producto
    const formProducto = document.getElementById('formAddProduct');
    if (formProducto) {
        formProducto.addEventListener('submit', function(e) {
            const id = document.getElementsByName('id_producto')[0].value;
            const confirmacion = confirm(`¿Estás seguro de registrar el producto ID: ${id} en el nodo actual?`);
            if (!confirmacion) {
                e.preventDefault();
            }
        });
    }

    // 3. Auto-ocultar alertas después de 5 segundos
    const alert = document.querySelector('.alert');
    if (alert) {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    }
});