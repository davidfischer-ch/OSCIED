<?php if ( ! defined('BASEPATH')) exit('No direct script access allowed');

class Transform extends MY_Controller
{

   protected $page_name = 'transform';

   public function __construct() {
      parent::__construct();
   }

   /**
    * TODO : comments
    */
   public function index() {
      $this->load->helper('number');
      $this->load->spark('restclient/2.1.0');
      $this->load->library('rest');
      $this->rest->initialize(
         array(
            'server' => $this->config->item('orchestra_api_url'), 'http_auth' => 'basic',
            'http_user' => $this->user->mail(), 'http_pass' => $this->user->secret()
         )
      );
      $response = $this->rest->get('transform/job');
      if ($response->status != 200) {
         print_r($response->value);
         exit;
      }
      $data['jobs'] = $response->value;
      // Get the medias for the dropdown
      $response = $this->rest->get('media/HEAD');
      if ($response->status != 200) {
         print_r($response->value);
         exit;
      }
      $data['medias'] = array();
      foreach ($response->value as $media) {
         $data['medias'][$media->_id] = $media->metadata->title.' - '.$media->virtual_filename;
      }
      // Get the profiles for the dropdown
      $response = $this->rest->get('transform/profile');
      if ($response->status != 200) {
         print_r($response->value);
         exit;
      }
      $data['profiles'] = array();
      foreach ($response->value as $profile) {
         $data['profiles'][$profile->_id] = $profile->title;
      }
      // Get the queues for the dropdown
      $response = $this->rest->get('transform/queue');
      if ($response->status != 200) {
         print_r($response->value);
         exit;
      }
      $data['queues'] = array();
      foreach ($response->value as $queue) {
         $data['queues'][$queue] = $queue;
      }

      $this->add_content('page_title', 'OSCIED - Transform Jobs');
      $this->add_view('main', 'transform/show', $data);

      $header_data['page'] = 'transform';
      $this->render($header_data);
   }

   /**
    * TODO : comments
    */
   public function refresh() {
      $this->load->helper('number');
      $this->load->spark('restclient/2.1.0');
      $this->load->library('rest');
      $this->rest->initialize(
         array(
            'server' => $this->config->item('orchestra_api_url'), 'http_auth' => 'basic',
            'http_user' => $this->user->mail(), 'http_pass' => $this->user->secret()
         )
      );
      $response = $this->rest->get('transform/job');
      if ($response->status != 200) {
         print_r($response->value);
         exit;
      }
      $data['jobs'] = $response->value;
      $this->load->view('transform/show_jobs', $data);
   }

   /**
    * TODO : comments
    */
   public function revoke($id) {
      $this->load->spark('restclient/2.1.0');
      $this->load->library('rest');
      $this->rest->initialize(
         array(
            'server' => $this->config->item('orchestra_api_url'), 'http_auth' => 'basic',
            'http_user' => $this->user->mail(), 'http_pass' => $this->user->secret()
         )
      );
      $response = $this->rest->delete('transform/job/id/'.$id);
      // Set error or information message
      if ($response->status == 200) {
         $this->session->set_flashdata('infos', $response->value);
         echo json_encode(array('redirect' => 'transform'));
      }
      else {
         $this->session->set_flashdata('errors', $response->value->description);
         echo json_encode(array('redirect' => 'transform'));
      }
   }

   /**
    * TODO : comments
    */
   public function launch_transform() {
      $this->load->helper('number');
      $this->load->library('form_validation');

      $form_id = $this->input->post('form_id');

      $this->form_validation->set_rules('media_in_id', 'Input Media', 'required');
      $this->form_validation->set_rules('profile_id', 'Profile', 'required');
      $this->form_validation->set_rules('virtual_filename', 'Virtual filename', 'required');
      $this->form_validation->set_rules('title', 'Media title', 'required');
      $this->form_validation->set_rules('queue', 'Queue', 'required');

      if ($this->form_validation->run() === FALSE) {
         $errors = validation_errors();
         echo json_encode(array('errors' => $errors));
      }
      else {
         $this->load->spark('restclient/2.1.0');
         $this->load->library('rest');
         $this->rest->initialize(
            array(
               'server' => $this->config->item('orchestra_api_url'), 'http_auth' => 'basic',
               'http_user' => $this->user->mail(), 'http_pass' => $this->user->secret()
            )
         );
         $params = json_encode(
            array(
               'media_in_id' => $this->input->post('media_in_id'),
               'profile_id' => $this->input->post('profile_id'),
               'virtual_filename' => $this->input->post('virtual_filename'),
               'metadata' => array('title' => $this->input->post('title')),
               'queue' => $this->input->post('queue')
            )
         );
         $response = $this->rest->post('transform/job', $params, 'json');
         if ($response->status == 200) {
            // Set the flash message
            $this->session->set_flashdata(
               'infos', 'The transform job for media "'.$this->input->post('title').' - '.
                  $this->input->post('virtual_filename').'" has been launched.'
            );
            echo json_encode(array('redirect' => site_url('transform')));
         }
         else {
            echo json_encode(array('errors' => $response->value->description));
         }
      }
   }

}

/* End of file transform.php */
/* Location: ./application/controllers/transform.php */